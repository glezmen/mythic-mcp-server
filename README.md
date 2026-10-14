# Mythic GM Emulator MCP Server

An MCP server for running a player-led Mythic GM Emulator session. It provides Fate Chart resolution, Random Event generation, scene checks, campaign state, and a session-oriented GM instruction reference.

## Included tools

### Core resolution
- `fate_question` — resolves a yes/no question using Odds, current Chaos Factor, D100 roll and exceptional boundaries; logs the result by default.
- `roll_d100` — roll 1D100.
- `check_random_event` — check whether a Fate roll is a qualifying double.
- `generate_random_event` — rolls Event Focus, Action Meaning and Subject Meaning. Rolls may be supplied for reproducibility.
- `scene_check` — Expected / Altered / Interrupt Scene.

### Session lifecycle and GM guidance
- `start_session` — initialize a new session and optional PC/opening situation.
- `reset_session` — reset state with an explicit confirmation argument.
- `get_gm_instructions` — returns the LLM operating procedure and source caveats.
- `get_rules_reference` — concise rules reference.
- `get_next_scene_guidance` — state-aware scene setup guidance.
- `get_session_summary` — compact state suitable for context injection.
- `get_session_state` — full persistent state.
- `mythic_gm_session` — MCP prompt template.

### Campaign state
- `set_session_name`, `set_chaos_factor`, `adjust_chaos_factor`
- `add_thread`, `close_thread`, `get_open_threads`
- `add_character`, `update_character`, `get_character_list`
- `add_established_fact`, `get_established_facts`
- `add_scene_note`
- `resolve_random_event` — records an LLM interpretation of an event.
- `end_scene` — records the scene, updates Chaos Factor based on control, increments scene number and prepares the next setup.
- `advance_scene` — compatibility helper without Chaos Factor adjustment.
- `list_meaning_tables`

## Fate Chart source

Odds arrays and the Exceptional Yes/No formulas are based on `MainActivity.java` from the supplied `assistant.zip`. The arrays use Chaos Factor order 1 through 9. Formula arithmetic follows Java integer division (truncate toward zero):

```text
exceptionalYes = yesChance / 5
exceptionalNo  = 100 - (100 - yesChance) / 5 + 1
```

The Android ZIP did not include the XML resources for the Action and Subject Meaning tables. The bundled word lists are convenience transcriptions from the project draft and **are not verified against that app's resources**. If exact source-edition table wording and ordering matter, compare these lists with the licensed Mythic edition you use. The underlying RPG still governs character creation, combat, skills, damage, etc.

## Install

Python 3.10+ recommended.

```bash
cd mythic_mcp_server
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

## Run

```bash
mythic-gm-mcp
```

Uses MCP stdio transport, intended for an MCP client to launch as a local process. State persists in `~/.mythic-gm-mcp/session.json` by default; override with `MYTHIC_STATE_FILE`.

## Generic MCP client config

```json
{
  "mcpServers": {
    "mythic-gm": {
      "command": "/absolute/path/to/mythic_mcp_server/.venv/bin/mythic-gm-mcp",
      "args": [],
      "env": {
        "MYTHIC_STATE_FILE": "/absolute/path/to/mythic-session.json"
      }
    }
  }
}
```

## Important operational note

Tools do not replace the LLM's judgment. The model chooses the Odds level, interprets the event words, narrates the fiction and asks the player what they do. It must use the tools to resolve randomness and maintain persistent state rather than silently inventing Fate results.
