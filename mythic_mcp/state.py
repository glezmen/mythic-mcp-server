"""JSON-persisted Mythic session state."""
from __future__ import annotations
import json
import os
import threading
from pathlib import Path
from typing import Any, Callable

DEFAULT_STATE: dict[str, Any] = {
    "session_name": "Mythic session",
    "active": False,
    "chaos_factor": 5,
    "scene_number": 0,
    "current_scene": None,
    "threads": [],
    "characters": [],
    "established_facts": [],
    "scene_log": [],
    "notes": [],
    "fate_log": [],
    "random_event_log": [],
    "created_at": None,
}

class SessionState:
    def __init__(self, path: str | None = None):
        default_path = Path.home() / ".mythic-gm-mcp" / "session.json"
        self.path = Path(path or os.environ.get("MYTHIC_STATE_FILE", str(default_path)))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        if not self.path.exists():
            self._write(DEFAULT_STATE.copy())
        self.data = self._read()

    def _read(self) -> dict[str, Any]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            # Migrate older state files without losing existing content.
            merged = DEFAULT_STATE.copy()
            if isinstance(raw, dict):
                merged.update(raw)
            return merged
        except (OSError, json.JSONDecodeError):
            return DEFAULT_STATE.copy()

    def _write(self, value: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            self.data = self._read()
            return json.loads(json.dumps(self.data, ensure_ascii=False))

    def update(self, fn: Callable[[dict[str, Any]], Any]) -> tuple[dict[str, Any], Any]:
        with self._lock:
            self.data = self._read()
            result = fn(self.data)
            self._write(self.data)
            return json.loads(json.dumps(self.data, ensure_ascii=False),), result

def next_id(items: list[dict[str, Any]], prefix: str) -> str:
    """Generate a non-colliding ID even if an earlier item was deleted."""
    used = {x.get("id") for x in items}
    n = 1
    while f"{prefix}-{n}" in used:
        n += 1
    return f"{prefix}-{n}"
