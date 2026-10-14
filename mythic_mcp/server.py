"""MCP server exposing tools for a complete Mythic GM Emulator session."""
from __future__ import annotations
from datetime import datetime, timezone
import random
from typing import Any
from mcp.server.mcpserver import MCPServer
from .data import ODDS, YES_CHANCES, fate_thresholds, ACTION_MEANINGS, SUBJECT_MEANINGS, EVENT_FOCUS
from .state import SessionState, next_id

mcp = MCPServer("mythic-gm-emulator")
state = SessionState()

def now():
    return datetime.now(timezone.utc).isoformat()

def _find(items, item_id):
    return next((item for item in items if item.get("id") == item_id), None)

def _record_note(d, text, kind="note"):
    d["notes"].append({"timestamp": now(), "scene": d.get("scene_number", 0), "kind": kind, "text": text})

@mcp.tool()
def get_gm_instructions() -> dict[str, Any]:
    """Return the operating procedure and rules summary an LLM needs to run a Mythic session."""
    return {
      "role": "You are the Mythic GM Emulator, not an author following a predetermined plot. Present fiction, adjudicate uncertainty fairly, and never decide the player character's actions or thoughts.",
      "core_loop": [
        "Track established facts, player character(s), NPCs/groups, open Threads, scene number, Chaos Factor (1..9), and unresolved questions.",
        "For obvious facts, use established fiction and logic without rolling. Use Fate Questions for meaningful uncertainties that can be phrased as yes/no.",
        "Choose Odds based on the fiction, independently from Chaos Factor. Call fate_question with the current Chaos Factor; let the tool roll unless the user supplied a roll.",
        "If the Fate roll triggers a Random Event, resolve and record the original Fate answer first, then call generate_random_event. Interpret its focus and two meaning words in context; do not force a literal reading.",
        "Set up a scene based on the previous scene, PC intent, and open Threads. Call scene_check with current Chaos Factor. Expected Scene follows setup; Altered Scene keeps the setup's purpose but changes an important circumstance; Interrupt Scene replaces the setup and should prompt a Random Event.",
        "Describe concrete sensory details and actionable choices. Do not reveal information the character cannot know. Keep the story moving; skip routine details.",
        "At the end of a scene, summarize what changed, update Threads/characters/facts, decide whether events were chaotic or under PC control, then call end_scene to update Chaos Factor and advance the scene.",
        "Use add_established_fact for consequential facts, add_thread/close_thread for goals, and add_character/update_character for recurring NPCs and groups. Record key developments in scene notes.",
        "Do not secretly reroll or manipulate outcomes to favor the PC. If a question is badly framed, reformulate it before rolling. Use 'I don't know' only when a Random Event has no sensible interpretation after a brief attempt.",
        "Sequential Fate Questions: Never issue multiple Fate Question tool calls in parallel. Submit exactly one Fate Question, wait for its result, interpret the outcome, resolve any triggered Random Event, and only then decide whether another question is needed."
      ],
      "fate_question": {
        "odds_levels": ODDS,
        "chaos_factor": "1..9; higher values affect Yes probabilities and scene changes.",
        "resolution": "The tool uses the supplied source app's Yes chance arrays and the exact integer arithmetic for Exceptional Yes/No thresholds. The underlying source has eleven Odds rows.",
        "random_event_trigger": "After resolving the Fate Question, a roll of 11,22,33,44,55,66,77,88,99 triggers a Random Event if the repeated digit is <= current Chaos Factor."
      },
      "scene_rules": {
        "scene_roll": "Roll 1D10. If roll > Chaos Factor: Expected Scene. Otherwise odd: Altered Scene; even: Interrupt Scene.",
        "chaos_update": "At scene end, increase Chaos Factor by 1 if events were chaotic and largely drove the PCs; decrease by 1 if the PCs controlled events. Clamp to 1..9. If neither clearly applies, leave it unchanged."
      },
      "random_event_focus": [{"range": f"{lo}-{hi}", "focus": name} for lo,hi,name in EVENT_FOCUS],
      "interpretation": "Random Event output is a prompt, not a finished plot. Focus identifies what is affected; Action and Subject words suggest what happens. The established fiction has priority over literal word matching.",
      "source_caveats": [
        "Fate odds arrays and exceptional threshold formulas were taken from MainActivity.java in the supplied assistant.zip.",
        "The supplied ZIP did not include the Android XML resources for the Action/Subject meaning tables. The bundled word lists are convenience transcriptions and should be checked against the exact Mythic edition if exact wording/order matters.",
        "This server implements Mythic adjudication tools; it does not replace the rules of the underlying RPG for combat, skills, damage, or character creation."
      ]
    }

@mcp.tool()
def start_session(session_name: str, chaos_factor: int = 5, opening_situation: str = "",
                  pc_name: str = "", pc_description: str = "", reset_existing: bool = False) -> dict[str, Any]:
    """Start a Mythic session. By default refuses to overwrite an active session; set reset_existing=true to replace it."""
    if not session_name.strip():
        return {"error": "session_name must not be empty"}
    if not 1 <= chaos_factor <= 9:
        return {"error": "chaos_factor must be 1..9"}
    current = state.snapshot()
    if current.get("active") and not reset_existing:
        return {"error": "An active session already exists. Use reset_session or set reset_existing=true explicitly."}
    new_state = {
      "session_name": session_name.strip(), "active": True, "chaos_factor": chaos_factor,
      "scene_number": 1, "current_scene": {"setup": opening_situation.strip(), "status": "in_progress"},
      "threads": [], "characters": [], "established_facts": [], "scene_log": [], "notes": [],
      "fate_log": [], "random_event_log": [], "created_at": now()
    }
    if pc_name.strip():
        new_state["characters"].append({
          "id": "character-1", "name": pc_name.strip(), "role": "PC",
          "description": pc_description.strip(), "goals": "", "notes": ""
        })
    if opening_situation.strip():
        new_state["established_facts"].append({
          "id": "fact-1", "fact": opening_situation.strip(), "source": "session setup",
          "timestamp": now(), "scene": 1
        })
    def replace(d):
        d.clear()
        d.update(new_state)
    result, _ = state.update(replace)
    return {"started": True, "state": result, "next_step": "Use get_gm_instructions, then get_next_scene_guidance to prepare the opening scene."}

@mcp.tool()
def reset_session(confirm: bool, session_name: str = "Mythic session", chaos_factor: int = 5) -> dict[str, Any]:
    """Reset all saved campaign state. Requires confirm=true to prevent accidental deletion."""
    if not confirm:
        return {"error": "No changes made. Call again with confirm=true to delete the current session state."}
    if not 1 <= chaos_factor <= 9:
        return {"error": "chaos_factor must be 1..9"}
    fresh = {"session_name": session_name.strip() or "Mythic session", "active": False,
             "chaos_factor": chaos_factor, "scene_number": 0, "current_scene": None,
             "threads": [], "characters": [], "established_facts": [], "scene_log": [],
             "notes": [], "fate_log": [], "random_event_log": [], "created_at": None}
    def replace(d):
        d.clear()
        d.update(fresh)
    result, _ = state.update(replace)
    return {"reset": True, "state": result}

@mcp.tool()
def get_session_state() -> dict[str, Any]:
    """Get the complete persisted session state."""
    return state.snapshot()

@mcp.tool()
def set_session_name(name: str) -> dict[str, Any]:
    """Rename the active session."""
    if not name.strip(): return {"error": "name must not be empty"}
    result, _ = state.update(lambda d: d.update({"session_name": name.strip()}))
    return result

@mcp.tool()
def set_chaos_factor(value: int) -> dict[str, Any]:
    """Set Chaos Factor to 1..9."""
    if not 1 <= value <= 9: return {"error": "Chaos Factor must be 1..9"}
    result, _ = state.update(lambda d: d.update({"chaos_factor": value}))
    return {"chaos_factor": result["chaos_factor"]}

@mcp.tool()
def adjust_chaos_factor(delta: int) -> dict[str, Any]:
    """Adjust Chaos Factor by -1 or +1, clamped to 1..9."""
    if delta not in (-1, 1): return {"error": "delta must be -1 or +1"}
    def change(d): d["chaos_factor"] = max(1, min(9, int(d.get("chaos_factor", 5)) + delta))
    result, _ = state.update(change)
    return {"chaos_factor": result["chaos_factor"]}

@mcp.tool()
def fate_question(odds: str, question: str = "", chaos_factor: int | None = None,
                  roll: int | None = None, record: bool = True) -> dict[str, Any]:
    """Resolve a Mythic yes/no Fate Question and optionally log it."""
    if odds not in YES_CHANCES: return {"error": "Unknown odds level", "valid_odds": list(YES_CHANCES)}
    if chaos_factor is None: chaos_factor = state.snapshot().get("chaos_factor", 5)
    if not 1 <= chaos_factor <= 9: return {"error": "chaos_factor must be 1..9"}
    if roll is None: roll = random.randint(1, 100)
    if not 1 <= roll <= 100: return {"error": "roll must be 1..100"}
    yes = YES_CHANCES[odds][chaos_factor - 1]
    ey, en = fate_thresholds(yes)
    if roll <= ey: result = "Exceptional Yes"
    elif roll >= en: result = "Exceptional No"
    elif roll <= yes: result = "Yes"
    else: result = "No"
    double = roll in {11,22,33,44,55,66,77,88,99}
    triggered = double and roll // 11 <= chaos_factor
    answer = {"question": question, "odds": odds, "chaos_factor": chaos_factor, "roll": roll,
              "yes_chance": yes, "exceptional_yes_threshold": ey,
              "exceptional_no_threshold": en, "result": result,
              "random_event_triggered": triggered}
    if record:
        def log(d):
            d["fate_log"].append({**answer, "timestamp": now(), "scene": d.get("scene_number", 0)})
        state.update(log)
    return answer

@mcp.tool()
def roll_d100() -> dict[str, int]:
    """Roll 1D100, returning an integer from 1 to 100."""
    return {"roll": random.randint(1, 100)}

@mcp.tool()
def check_random_event(roll: int, chaos_factor: int | None = None) -> dict[str, Any]:
    """Check a Fate roll for a Random Event double. The Fate answer should be resolved first."""
    if chaos_factor is None: chaos_factor = state.snapshot().get("chaos_factor", 5)
    if not 1 <= chaos_factor <= 9: return {"error": "chaos_factor must be 1..9"}
    if not 1 <= roll <= 100: return {"error": "roll must be 1..100"}
    double = roll in {11,22,33,44,55,66,77,88,99}
    digit = roll // 11 if double else None
    return {"roll": roll, "chaos_factor": chaos_factor, "is_double": double,
            "repeated_digit": digit, "triggered": bool(double and digit <= chaos_factor),
            "instruction": "Resolve and record the Fate answer first; generate the Random Event afterward."}

@mcp.tool()
def generate_random_event(focus_roll: int | None = None, action_roll: int | None = None,
                          subject_roll: int | None = None, context: str = "") -> dict[str, Any]:
    """Roll Event Focus, Action Meaning, Subject Meaning; optionally supply rolls for reproducibility."""
    rolls = [focus_roll, action_roll, subject_roll]
    if any(r is not None and not 1 <= r <= 100 for r in rolls):
        return {"error": "All supplied rolls must be integers from 1 to 100"}
    fr = focus_roll if focus_roll is not None else random.randint(1,100)
    ar = action_roll if action_roll is not None else random.randint(1,100)
    sr = subject_roll if subject_roll is not None else random.randint(1,100)
    focus = next(name for lo,hi,name in EVENT_FOCUS if lo <= fr <= hi)
    event = {"focus_roll": fr, "focus": focus, "action_roll": ar, "action": ACTION_MEANINGS[ar-1],
             "subject_roll": sr, "subject": SUBJECT_MEANINGS[sr-1], "context": context,
             "instruction": "Interpret focus + action + subject using established facts, current scene, open Threads and PC intentions. Do not force literal interpretation."}
    def log(d):
        d["random_event_log"].append({**event, "timestamp": now(), "scene": d.get("scene_number", 0)})
    state.update(log)
    return event

@mcp.tool()
def scene_check(chaos_factor: int | None = None, roll: int | None = None) -> dict[str, Any]:
    """Check next scene: Expected if D10 > Chaos Factor; otherwise odd=Altered, even=Interrupt."""
    if chaos_factor is None: chaos_factor = state.snapshot().get("chaos_factor", 5)
    if not 1 <= chaos_factor <= 9: return {"error": "chaos_factor must be 1..9"}
    if roll is None: roll = random.randint(1,10)
    if not 1 <= roll <= 10: return {"error": "roll must be 1..10"}
    if roll > chaos_factor: outcome = "Expected Scene"
    elif roll % 2: outcome = "Altered Scene"
    else: outcome = "Interrupt Scene"
    return {"roll": roll, "chaos_factor": chaos_factor, "outcome": outcome,
            "next_action": "Generate a Random Event to replace the planned setup." if outcome == "Interrupt Scene" else "Describe the opening situation and let PC choices shape events."}

@mcp.tool()
def get_next_scene_guidance() -> dict[str, Any]:
    """Return state-aware guidance for setting up the next scene and the current lists."""
    d = state.snapshot()
    open_threads = [t for t in d["threads"] if t.get("status") == "open"]
    return {
      "session_name": d["session_name"], "active": d["active"], "scene_number": d["scene_number"],
      "chaos_factor": d["chaos_factor"], "current_scene": d.get("current_scene"),
      "open_threads": open_threads, "characters": d["characters"],
      "established_facts": d["established_facts"][-20:],
      "guidance": [
        "Choose a scene setup that follows from the previous scene, player intentions, and open Threads. The setup establishes the opening situation, not its outcome.",
        "If the next scene is uncertain, propose a plausible setup and call scene_check using the current Chaos Factor.",
        "Expected Scene: use the setup. Altered Scene: keep its core purpose but change an important circumstance. Interrupt Scene: discard the setup and generate a Random Event.",
        "Do not force a Thread onto the PC. Present concrete options and let the player choose."
      ]
    }

@mcp.tool()
def resolve_random_event(focus: str, action: str, subject: str, context: str = "",
                         interpretation: str = "", related_thread_id: str = "",
                         related_character_id: str = "") -> dict[str, Any]:
    """Record and structure an LLM interpretation of a rolled Random Event; does not invent the interpretation."""
    if not focus.strip() or not action.strip() or not subject.strip():
        return {"error": "focus, action, and subject are required"}
    result_event = {"focus": focus, "action": action, "subject": subject, "context": context,
                    "interpretation": interpretation, "related_thread_id": related_thread_id or None,
                    "related_character_id": related_character_id or None, "timestamp": now(),
                    "scene": state.snapshot().get("scene_number", 0)}
    def log(d): d["random_event_log"].append(result_event)
    state.update(log)
    return {"recorded": True, "event": result_event,
            "follow_up": "If the interpretation establishes a consequential new fact, call add_established_fact. Update Threads or Characters if the event changes them."}

@mcp.tool()
def add_thread(name: str, description: str = "", priority: str = "normal") -> dict[str, Any]:
    """Add an open Thread (an unresolved goal or story question)."""
    if not name.strip(): return {"error": "Thread name must not be empty"}
    created = {}
    def add(d):
        item = {"id": next_id(d["threads"], "thread"), "name": name.strip(),
                "description": description.strip(), "priority": priority, "status": "open",
                "created_scene": d.get("scene_number", 0)}
        d["threads"].append(item); created.update(item)
    state.update(add)
    return {"added": created}

@mcp.tool()
def close_thread(thread_id: str, outcome: str = "") -> dict[str, Any]:
    """Close an open Thread and record how it ended."""
    result_obj = {}
    def close(d):
        item = _find(d["threads"], thread_id)
        if item:
            item["status"] = "closed"; item["outcome"] = outcome
            item["closed_scene"] = d.get("scene_number", 0)
            result_obj.update(item)
    state.update(close)
    return {"closed": result_obj} if result_obj else {"error": f"No Thread found with id {thread_id!r}"}

@mcp.tool()
def get_open_threads() -> dict[str, Any]:
    """List only open Threads."""
    d = state.snapshot()
    return {"threads": [t for t in d["threads"] if t.get("status") == "open"]}

@mcp.tool()
def add_character(name: str, description: str = "", role: str = "NPC",
                  goals: str = "", notes: str = "") -> dict[str, Any]:
    """Add a PC, NPC, organization, community, or independently acting group."""
    if not name.strip(): return {"error": "Character name must not be empty"}
    created = {}
    def add(d):
        item = {"id": next_id(d["characters"], "character"), "name": name.strip(),
                "description": description.strip(), "role": role.strip(), "goals": goals.strip(),
                "notes": notes.strip(), "status": "active", "created_scene": d.get("scene_number", 0)}
        d["characters"].append(item); created.update(item)
    state.update(add)
    return {"added": created}

@mcp.tool()
def get_character_list(include_inactive: bool = False) -> dict[str, Any]:
    """List the Character List, including PCs, NPCs, groups and their motivations."""
    d = state.snapshot()
    chars = d["characters"] if include_inactive else [c for c in d["characters"] if c.get("status","active") == "active"]
    return {"characters": chars}

@mcp.tool()
def update_character(character_id: str, description: str | None = None,
                     goals: str | None = None, notes: str | None = None,
                     status: str | None = None) -> dict[str, Any]:
    """Update a character's description, goals, notes, or active/inactive status."""
    changed = {}
    def update(d):
        item = _find(d["characters"], character_id)
        if item:
            if description is not None: item["description"] = description
            if goals is not None: item["goals"] = goals
            if notes is not None: item["notes"] = notes
            if status is not None:
                if status not in ("active","inactive","dead","departed"): return
                item["status"] = status
            changed.update(item)
    state.update(update)
    return {"updated": changed} if changed else {"error": f"No character found or invalid status for {character_id!r}"}

@mcp.tool()
def add_established_fact(fact: str, source: str = "in play") -> dict[str, Any]:
    """Record a consequential established fact so future rulings remain consistent."""
    if not fact.strip(): return {"error": "fact must not be empty"}
    created = {}
    def add(d):
        item = {"id": next_id(d["established_facts"], "fact"), "fact": fact.strip(),
                "source": source.strip(), "timestamp": now(), "scene": d.get("scene_number", 0)}
        d["established_facts"].append(item); created.update(item)
    state.update(add)
    return {"added": created}

@mcp.tool()
def get_established_facts(limit: int = 100) -> dict[str, Any]:
    """Return established facts in chronological order."""
    d = state.snapshot()
    limit = max(1, min(500, limit))
    return {"facts": d["established_facts"][-limit:]}

@mcp.tool()
def add_scene_note(note: str, kind: str = "note") -> dict[str, Any]:
    """Append a dated note to the session log."""
    if not note.strip(): return {"error": "note must not be empty"}
    created = {}
    def add(d):
        item = {"timestamp": now(), "scene": d.get("scene_number", 0), "kind": kind, "text": note.strip()}
        d["notes"].append(item); created.update(item)
    state.update(add)
    return {"added": created}

@mcp.tool()
def end_scene(summary: str, control: str = "unchanged", next_setup: str = "") -> dict[str, Any]:
    """End the current scene, record its summary, update Chaos Factor and prepare the next scene.

    control must be 'chaotic' (increase CF), 'controlled' (decrease CF), or 'unchanged'.
    """
    if control not in ("chaotic","controlled","unchanged"):
        return {"error": "control must be chaotic, controlled, or unchanged"}
    ended = {}
    def finish(d):
        old_scene = int(d.get("scene_number", 0))
        old_cf = int(d.get("chaos_factor", 5))
        if control == "chaotic": new_cf = min(9, old_cf + 1)
        elif control == "controlled": new_cf = max(1, old_cf - 1)
        else: new_cf = old_cf
        ended_entry = {"scene": old_scene, "summary": summary.strip(), "control": control,
                       "chaos_factor_before": old_cf, "chaos_factor_after": new_cf,
                       "ended_at": now()}
        d["scene_log"].append(ended_entry)
        d["chaos_factor"] = new_cf
        d["scene_number"] = old_scene + 1
        d["current_scene"] = {"setup": next_setup.strip(), "status": "ready"}
        ended.update(ended_entry)
    result, _ = state.update(finish)
    return {"ended_scene": ended, "next_scene_number": result["scene_number"],
            "chaos_factor": result["chaos_factor"], "current_scene": result["current_scene"],
            "next_step": "Call get_next_scene_guidance, then scene_check before playing the next scene."}

@mcp.tool()
def advance_scene(summary: str = "") -> dict[str, Any]:
    """Compatibility helper: advance the scene without applying a Chaos Factor adjustment."""
    return end_scene(summary=summary, control="unchanged")

@mcp.tool()
def list_meaning_tables() -> dict[str, Any]:
    """Return the bundled Random Event tables, their rolls, and provenance caveat."""
    return {
      "event_focus": [{"range": f"{lo}-{hi}", "focus": name} for lo,hi,name in EVENT_FOCUS],
      "action_meaning_count": len(ACTION_MEANINGS),
      "subject_meaning_count": len(SUBJECT_MEANINGS),
      "provenance_warning": "The supplied assistant.zip did not include the Android XML resources for Action/Subject meaning tables. Bundled word order is a convenience transcription, not source-verified against that app. Check against your licensed Mythic edition.",
      "recommended_tool": "generate_random_event"
    }

@mcp.tool()
def get_rules_reference() -> dict[str, Any]:
    """Return concise operational rules for Fate Questions, Random Events, Scenes, Threads, Characters and Chaos."""
    return {
      "fate_question": {
        "purpose": "Resolve one meaningful uncertainty phrased as a yes/no question.",
        "procedure": ["Phrase one clear yes/no question.", "Choose Odds based on established fiction.", "Use current Chaos Factor separately.", "Roll 1D100 and resolve using fate_question.", "Record the answer before any Random Event."],
        "odds": ODDS,
        "exceptional_formula": ["EY = Java-trunc(P / 5)", "EN = 101 - Java-trunc((100 - P) / 5)"],
        "random_event_trigger": "A double 11,22,...,99 triggers when its repeated digit <= current Chaos Factor."
      },
      "scenes": {
        "procedure": ["Set up a plausible next scene from player intent, previous events and open Threads.", "Roll D10 using scene_check.", "If roll > Chaos Factor, Expected Scene.", "Otherwise odd = Altered Scene; even = Interrupt Scene.", "Interrupt Scene replaces setup and prompts a Random Event."],
        "end": "At scene end, summarize consequences and update state. Increase Chaos Factor if events were chaotic; decrease if PCs controlled events; otherwise unchanged. Clamp to 1..9."
      },
      "random_event": "Roll Event Focus, Action Meaning and Subject Meaning. Interpret in context; tables are prompts, not literal instructions. If no reasonable interpretation fits after brief effort, discard the event and continue.",
      "threads": "Track unresolved goals/mysteries. Add meaningful goals, close resolved or irrelevant ones, do not force the PC to pursue every Thread.",
      "characters": "Track important PCs, NPCs, groups and independently acting entities with motives, abilities, relationships and resources. Random NPC Action should select from the Character List.",
      "world_consistency": "Record consequential facts. Use logic for obvious details; use Fate Questions for important uncertainties. Do not roll for trivial details.",
      "underlying_rpg": "Mythic adjudicates the world and unexpected developments; the underlying RPG governs character creation, combat, skills, damage and other system-specific mechanics."
    }

@mcp.tool()
def get_session_summary() -> dict[str, Any]:
    """Return a compact state snapshot suitable for injecting into an LLM context."""
    d = state.snapshot()
    return {
      "session_name": d["session_name"], "active": d["active"],
      "scene_number": d["scene_number"], "chaos_factor": d["chaos_factor"],
      "current_scene": d["current_scene"],
      "open_threads": [t for t in d["threads"] if t.get("status") == "open"],
      "active_characters": [c for c in d["characters"] if c.get("status","active") == "active"],
      "recent_facts": d["established_facts"][-15:],
      "recent_scene_log": d["scene_log"][-5:],
      "recent_fate_log": d["fate_log"][-5:],
      "recent_random_events": d["random_event_log"][-5:],
      "recent_notes": d["notes"][-10:]
    }

@mcp.prompt()
def mythic_gm_session() -> str:
    """Prompt template for an LLM acting as a Mythic GM Emulator."""
    return """You are running a player-led Mythic GM Emulator session. Use the MCP tools to maintain authoritative state.
At session start, call get_gm_instructions and get_rules_reference, then start_session if no active session exists.
Before a new scene, call get_next_scene_guidance and scene_check. For meaningful uncertainties, call fate_question with a clearly framed yes/no question and the current Chaos Factor. If its result triggers a Random Event, record the Fate answer first, then call generate_random_event and interpret it in context.
At scene end, call end_scene with a concise summary and control='chaotic', 'controlled', or 'unchanged'; update facts, Threads, and Characters with tools.
Narrate what the PC perceives, provide actionable choices, never decide the PC's actions or thoughts, do not reveal unknown information, and do not force a predetermined plot. Keep state consistent and avoid rolling for trivial facts."""

def main():
    mcp.run(transport="stdio")

if __name__ == "__main__":
    main()
