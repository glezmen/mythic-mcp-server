#!/usr/bin/env python3
"""Two-agent Mythic prototype for one LM Studio model. Python 3.10+, requests."""
import argparse, asyncio, json, os, random, re, shlex, sys, time
from pathlib import Path
from threading import Thread
from queue import Queue
import requests
import traceback

DEFAULT_URL = "http://localhost:1234/v1"
DEFAULT_MODEL = "qwen3.8-27b-splash"

GM_SYSTEM = """You are the Game Master for a player-led Mythic roleplaying session.
At the beginning of a new campaign, invent a fresh, coherent world, setting, genre, tone, starting situation, and a possible player-character concept. Do not reuse a predefined campaign, setting, mystery, character, or plot. Nothing has been chosen in advance.
The Player agent decides what character they want to play and may accept, refine, or reject the proposed concept or ask for alternatives. Never dictate the player's character choices.
Keep the story open-ended and reactive. Present what the character can perceive and let the Player agent decide what to do. Never decide the character's actions, thoughts, or feelings.
Use the Mythic MCP server as the authoritative rules and campaign-state engine. Discover its available tools and schemas at runtime. Use its Fate Question, Random Event, scene, Chaos Factor, and state tools when appropriate. Do not invent tool names or arguments, and do not replace MCP mechanics with locally hardcoded tables or dice rules.
"""
PLAYER_SYSTEM = """You are the Player agent in a Mythic roleplaying session.
When a new campaign begins, respond to the GM's proposed world and character concept. Decide what sort of character you want to play; you may accept, refine, or reject the proposal and request alternatives. Do not assume a setting or character was selected in advance.
During play, independently invent the character's actions from their goals, personality, knowledge, capabilities, and the current situation. There is no predefined action list or action sequence.
Do not decide uncertain world outcomes yourself, do not invent facts the character could not know, and do not direct the GM. The GM adjudicates the world, with Mythic MCP tools maintaining rules and state.
"""

def save(path, state):
    tmp=Path(str(path)+".tmp"); tmp.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding="utf-8"); tmp.replace(path)
def log(path, data):
    with open(path,"a",encoding="utf-8") as f:
        f.write(json.dumps({"time":time.strftime("%Y-%m-%dT%H:%M:%S%z"),**data},ensure_ascii=False)+"\n")
def log_dialogue(path, role, text, turn=None):
    """Append only player-facing GM/Player dialogue to a separate file."""
    if not path:
        return
    entry = {
        "time": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "role": role,
        "text": text,
    }
    if turn is not None:
        entry["turn"] = turn
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def new_state():
    """Empty bootstrap. The GM and Player agents establish the campaign from scratch."""
    return {
        "campaign": "",
        "language": "",
        "chaos_factor": 5,
        "scene_number": 0,
        "character": {},
        "threads": [],
        "npcs": [],
        "known_facts": [],
        "gm_notes": [],
        "current_scene": "",
        "last_gm": "",
        "scene_control": "new",
    }


class Client:
    def __init__(self,url,model,temperature,max_tokens,timeout):
        self.url=url.rstrip("/"); self.model=model; self.temperature=temperature
        self.max_tokens=max_tokens; self.timeout=timeout
    def chat(self,messages):
        r=requests.post(self.url+"/chat/completions",json={"model":self.model,"messages":messages,
          "temperature":self.temperature,"max_tokens":self.max_tokens,"stream":False},timeout=self.timeout)
        if not r.ok: raise RuntimeError(f"LM Studio HTTP {r.status_code}: {r.text[:1000]}")
        return str(r.json()["choices"][0]["message"].get("content") or "").strip()

def call(client, role, history, prompt):
    system=GM_SYSTEM if role=="GM" else PLAYER_SYSTEM
    answer=client.chat([{"role":"system","content":system},*history,{"role":"user","content":prompt}])
    history.extend([{"role":"user","content":prompt},{"role":"assistant","content":answer}])
    return answer


class MythicMCPBridge:
    """Persistent stdio MCP client. Requires the official Python MCP SDK (`mcp`)."""
    def __init__(self, command, args=None, env=None, cwd=None):
        self.command = command
        self.args = args or []
        self.env = env
        self.cwd = cwd or os.getcwd()
        self.requests = Queue()
        self.ready = Queue()
        self.thread = Thread(target=self._thread_main, daemon=True)
        self.thread.start()
        ok, detail = self.ready.get(timeout=30)
        if not ok:
            raise RuntimeError(detail)
        self.tools = detail

    def _thread_main(self):
        async def worker():
            try:
                from mcp import ClientSession, StdioServerParameters
                from mcp.client.stdio import stdio_client
                params = StdioServerParameters(
                    command=self.command,
                    args=self.args,
                    env=self.env,
                    cwd=self.cwd,
                )
                async with stdio_client(params) as (read_stream, write_stream):
                    async with ClientSession(read_stream, write_stream) as session:
                        await session.initialize()
                        tool_result = await session.list_tools()
                        tools = []
                        for tool in tool_result.tools:
                            tools.append({
                                "name": tool.name,
                                "description": tool.description or "",
                                "inputSchema": tool.input_schema,
                            })
                        self.ready.put((True, tools))
                        while True:
                            item = await asyncio.to_thread(self.requests.get)
                            if item is None:
                                return
                            request_id, name, arguments = item
                            try:
                                result = await session.call_tool(name, arguments)
                                parts = []
                                for content in getattr(result, "content", []) or []:
                                    if getattr(content, "text", None) is not None:
                                        parts.append(content.text)
                                    else:
                                        parts.append(str(content))
                                payload = {
                                    "isError": bool(getattr(result, "isError", False)),
                                    "content": parts,
                                    "structuredContent": getattr(result, "structuredContent", None),
                                }
                                self.requests_results.put((request_id, True, payload))
                            except Exception as exc:
                                self.requests_results.put((request_id, False, str(exc)))
            except Exception as exc:
                traceback.print_exc()
                try:
                    self.ready.put((
                        False,
                        f"MCP start error: {exc!r}"
                    ))
                except Exception:
                    pass

        self.requests_results = Queue()
        asyncio.run(worker())

    def call(self, name, arguments):
        request_id = str(time.time_ns())
        self.requests.put((request_id, name, arguments))
        while True:
            rid, ok, result = self.requests_results.get(timeout=600)
            if rid == request_id:
                if not ok:
                    raise RuntimeError(f"MCP tool '{name}' error: {result}")
                return result
            self.requests_results.put((rid, ok, result))
            time.sleep(0.01)

    def close(self):
        self.requests.put(None)


def mcp_tool_catalog(bridge):
    return "\n".join(
        f"- {t['name']}: {t['description']} | inputSchema={json.dumps(t['inputSchema'], ensure_ascii=False)}"
        for t in bridge.tools
    )


def parse_tool_markup(text, known_tools):
    """Parse tool-call markup emitted as plain text by models that do not use API tool calling."""
    patterns = [
        r"<tool_call>\s*(.*?)\s*</tool_call>",
        r"<invoke>\s*(.*?)\s*</invoke>",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.I | re.S):
            raw = match.group(1).strip()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue

            # Models use several incompatible plain-text formats.
            name = data.get("name") or data.get("tool") or data.get("function")
            arguments = data.get("arguments", data.get("parameters", {}))
            if isinstance(name, dict):
                arguments = name.get("arguments", arguments)
                name = name.get("name")
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    continue
            if name in known_tools and isinstance(arguments, dict):
                return {"call_tool": True, "name": name, "arguments": arguments,
                        "purpose": "Parsed tool-call markup emitted by the model."}
    return None


def choose_tool_call(client, history, tools_text, action_text):
    """Ask the GM to select a valid MCP tool call when one is needed."""
    prompt = (
        "Available Mythic MCP tools and their schemas:\\n"
        + tools_text
        + "\\n\\nPlayer action or situation raised by the GM:\\n"
        + action_text
        + "\\n\\nDecide whether a Mythic MCP tool needs to be called NOW. "
        "If a tool call is needed, return ONLY valid JSON in this format: "
        '{"call_tool": true, "name": "exact_tool_name", '
        '"arguments": {...}, "purpose": "brief explanation"}. '
        "Use an existing tool name exactly as listed and provide arguments "
        "that conform to its schema. Do not invent tool names or arguments. "
        'If no tool call is needed, return {"call_tool": false}.'
    )

    raw = client.chat([
        {"role": "system", "content": (
            "You are a strict MCP tool selector. Return valid JSON only, "
            "with no Markdown or additional text."
        )},
        {"role": "user", "content": prompt},
    ])

    known = {tool["name"] for tool in getattr(client, "mcp_tools", [])}
    parsed_markup = parse_tool_markup(raw, known)
    if parsed_markup:
        return parsed_markup

    match = re.search(r"\{.*\}", raw, re.S)
    if not match:
        return {"call_tool": False}
    try:
        data = json.loads(match.group())
        if (data.get("call_tool") is True and data.get("name") in known
                and isinstance(data.get("arguments"), dict)):
            return data
    except (json.JSONDecodeError, TypeError, AttributeError):
        pass
    return {"call_tool": False}


def strip_tool_markup(text):
    """Remove tool-call/control markup so it is never shown as player-facing narration."""
    text = re.sub(r"<tool_call>.*?</tool_call>", "", text, flags=re.I | re.S)
    text = re.sub(r"<invoke>.*?</invoke>", "", text, flags=re.I | re.S)
    text = re.sub(r"<function_results>.*?</function_results>", "", text, flags=re.I | re.S)
    return text.strip()


def main():
    parser = argparse.ArgumentParser(
        description="Run a GM agent and a Player agent against LM Studio and Mythic MCP."
    )
    parser.add_argument("--base-url", default=os.getenv("LM_STUDIO_BASE_URL", DEFAULT_URL))
    parser.add_argument("--model", default=os.getenv("LM_STUDIO_MODEL", DEFAULT_MODEL))
    parser.add_argument("--state", default="game_state.json")
    parser.add_argument("--log", default="game_log.jsonl")
    parser.add_argument(
        "--conversation-log",
        metavar="FILE",
        default=None,
        help="Write only the GM/Player dialogue to FILE (no MCP, routing, or internal logs).",
    )
    parser.add_argument("--new", action="store_true", help="Start a fresh campaign.")
    parser.add_argument(
        "--manual-player",
        action="store_true",
        help="Enter player actions yourself instead of using the Player agent.",
    )
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--max-tokens", type=int, default=1800)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--max-turns", type=int, default=0, help="Stop after this many self-play turns; 0 means unlimited.")
    parser.add_argument(
        "--mcp-command",
        default=f"{shlex.quote(sys.executable)} -m mythic_mcp.server",
        help="Command used to start the Mythic MCP server.",
    )
    parser.add_argument(
        "--mcp-arg",
        action="append",
        default=[],
        help="Additional MCP server argument; may be specified more than once.",
    )
    parser.add_argument(
        "--no-mcp",
        action="store_true",
        help="Disable Mythic MCP. Mythic mechanics will not be resolved.",
    )
    args = parser.parse_args()

    state_path = Path(args.state)
    log_path = Path(args.log)

    state = (
        new_state()
        if args.new or not state_path.exists()
        else json.loads(state_path.read_text(encoding="utf-8"))
    )

    client = Client(
        args.base_url,
        args.model,
        args.temperature,
        args.max_tokens,
        args.timeout,
    )

    bridge = None
    tools_text = ""

    if not args.no_mcp:
        try:
            command_parts = shlex.split(args.mcp_command)
            if not command_parts:
                raise ValueError("--mcp-command must not be empty.")

            bridge = MythicMCPBridge(
                command_parts[0],
                command_parts[1:] + args.mcp_arg,
                cwd=str(Path(__file__).resolve().parent),
            )
            client.mcp_tools = bridge.tools
            tools_text = mcp_tool_catalog(bridge)

            print(
                "Mythic MCP connected. Available tools:",
                ", ".join(tool["name"] for tool in bridge.tools),
            )
        except Exception as exc:
            print(f"Could not start Mythic MCP: {exc}", file=sys.stderr)
            print(
                "Check --mcp-command, the repository environment, and the installed "
                "MCP SDK. Use --no-mcp only for testing without Mythic mechanics.",
                file=sys.stderr,
            )
            return 3

    try:
        try:
            response = requests.get(
                args.base_url.rstrip("/") + "/models",
                timeout=10,
            )
            response.raise_for_status()
            models = response.json().get("data", [])
            print(
                "LM Studio models:",
                ", ".join(model.get("id", "?") for model in models) or "(none listed)",
            )
        except Exception as exc:
            print(f"Cannot reach the LM Studio API: {exc}", file=sys.stderr)
            return 2

        print(f"\nMythic GM + Player | model={args.model} | API={args.base_url}")
        print("Commands: /quit, /save, /status")
        print("Mode:", "manual player" if args.manual_player else "AI player")

        gm_history = []
        player_history = []

        def resolve_mcp_if_needed(gm_text, context):
            """Execute model-emitted or selector-chosen MCP calls, then ask GM to narrate."""
            if not bridge:
                return strip_tool_markup(gm_text)

            known_tools = {tool["name"] for tool in bridge.tools}
            original_text = gm_text
            pending_text = gm_text
            fate_match = re.search(
                r"\[FATE:\s*(.*?)\s*\|\s*(.*?)\s*\]",
                pending_text, re.I | re.S,
            )

            # Parse plain-text tool-call markup emitted by local models first.
            selection = parse_tool_markup(pending_text, known_tools)
            if not selection:
                if fate_match:
                    tool_context = (
                        "Resolve this Fate Question through the Mythic MCP server. "
                        "Question: " + fate_match.group(1).strip()
                        + "; odds: " + fate_match.group(2).strip()
                        + ". Select the appropriate available tool and schema-valid arguments."
                    )
                else:
                    tool_context = (
                        "Review the GM output and current turn to decide whether a Mythic "
                        "MCP tool call is required now. Do not call a tool merely for narration.\n"
                        "Turn context:\n" + context + "\nGM output:\n" + pending_text
                    )
                selection = choose_tool_call(client, gm_history, tools_text, tool_context)

            if not selection.get("call_tool"):
                if fate_match:
                    print(
                        "No MCP tool was selected for the Fate Question; "
                        "no local roll was substituted.", file=sys.stderr, flush=True,
                    )
                return strip_tool_markup(re.sub(
                    r"\[FATE:.*?\]", "", pending_text, flags=re.I | re.S
                ))

            # A follow-up can emit another tool call. Limit chaining to avoid loops.
            for _ in range(5):
                try:
                    name = selection["name"]
                    arguments = selection.get("arguments", {})
                    print(f"[MCP] Calling {name} with {json.dumps(arguments, ensure_ascii=False)}", flush=True)
                    result = bridge.call(name, arguments)
                    print(f"[MCP] {name} completed.", flush=True)
                    log(log_path, {
                        "role": "MCP", "tool": name, "arguments": arguments,
                        "purpose": selection.get("purpose", ""), "result": result,
                    })
                    follow_up = (
                        "An authoritative Mythic MCP tool has returned this result. "
                        "Treat the result as authoritative; do not change or reroll it. "
                        "Continue the scene in the language already used in the session. "
                        "Write player-facing narration only. Do not output tool-call markup.\n"
                        + json.dumps({"tool": name, "result": result}, ensure_ascii=False)
                        + "\nOriginal GM output/context:\n" + original_text
                        + "\nTurn context:\n" + context
                    )
                    updated = call(client, "GM", gm_history, follow_up)
                    next_selection = parse_tool_markup(updated, known_tools)
                    if next_selection:
                        original_text = updated
                        selection = next_selection
                        continue
                    return strip_tool_markup(re.sub(
                        r"\[FATE:.*?\]", "", updated, flags=re.I | re.S
                    ))
                except Exception as exc:
                    log(log_path, {
                        "role": "MCP_ERROR", "tool": selection.get("name"),
                        "error": str(exc),
                    })
                    print(f"MCP tool call failed: {exc}", file=sys.stderr, flush=True)
                    return strip_tool_markup(original_text)

            print("[MCP] Stopped after 5 consecutive tool calls to prevent a loop.", file=sys.stderr, flush=True)
            return strip_tool_markup(original_text)


        if not state.get("last_gm"):
            opening_prompt = (
                "This is a completely new campaign. No setting, genre, plot, character, "
                "or language has been predefined. Invent a fresh and coherent world, "
                "genre, tone, and opening situation. Propose a possible player-character "
                "concept, but let the Player agent accept, refine, reject, or replace it. "
                "Present the opening situation and invite the player to decide what to do. "
                "Use available Mythic MCP tools when a game mechanic or persistent "
                "campaign-state operation actually requires one."
            )

            gm_text = call(client, "GM", gm_history, opening_prompt)
            gm_text = resolve_mcp_if_needed(gm_text, "New campaign opening.")

            state["last_gm"] = gm_text
            state["scene_number"] = int(state.get("scene_number", 0)) + 1

            print("\n=== GM ===\n" + gm_text, flush=True)
            log(log_path, {"role": "GM", "text": gm_text})
            log_dialogue(args.conversation_log, "GM", gm_text, turn=0)
            save(state_path, state)

        turn_count = 0
        print("Autonomous self-play enabled. Press Ctrl+C to stop.")

        while args.max_turns <= 0 or turn_count < args.max_turns:
            turn_count += 1

            player_prompt = (
                "Continue the autonomous roleplaying session. Based on the GM's latest "
                "narration, independently decide what your character does next. If the "
                "character concept has not yet been settled, accept, refine, or reject "
                "the proposal and then choose an action. Do not decide uncertain outcomes; "
                "state only the character's intended action. Do not ask the human for input. "
                "Keep the action appropriate to the character's goals, knowledge, and the "
                "current situation.\n\nGM narration:\n"
                + state.get("last_gm", "")
            )

            player_action = call(client, "Player", player_history, player_prompt)
            print(f"\n=== Player (turn {turn_count}) ===\n{player_action}", flush=True)
            log(log_path, {"role": "Player", "turn": turn_count, "text": player_action})
            log_dialogue(args.conversation_log, "Player", player_action, turn=turn_count)

            gm_prompt = (
                "Continue the autonomous roleplaying session in the language already "
                "established. Respond to the player's intended action, describe what "
                "follows from the fiction and authoritative Mythic MCP results, and then "
                "leave a clear situation for the Player agent's next decision. Do not "
                "invent a result for a mechanic that should be resolved by Mythic MCP. "
                "If a Fate Question is needed, mark it exactly as [FATE: question | odds] "
                "and do not decide its outcome. Never emit tool-call markup. Do not ask "
                "the human for input; this is autonomous agent-vs-agent play.\n\n"
                "Previous GM narration:\n"
                + state.get("last_gm", "")
                + "\n\nPlayer action:\n"
                + player_action
            )

            gm_text = call(client, "GM", gm_history, gm_prompt)
            gm_text = resolve_mcp_if_needed(
                gm_text,
                "Player action:\n"
                + player_action
                + "\nPrevious scene:\n"
                + state.get("last_gm", ""),
            )

            print(f"\n=== GM (turn {turn_count}) ===\n{gm_text}", flush=True)
            log(log_path, {"role": "GM", "turn": turn_count, "text": gm_text})
            log_dialogue(args.conversation_log, "GM", gm_text, turn=turn_count)

            state["last_gm"] = gm_text
            state["scene_number"] = int(state.get("scene_number", 0)) + 1
            save(state_path, state)

        if args.max_turns > 0:
            print(f"Reached --max-turns={args.max_turns}; stopping self-play.")

    finally:
        if bridge:
            bridge.close()

    save(state_path, state)
    print(f"Saved campaign state to {state_path}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
