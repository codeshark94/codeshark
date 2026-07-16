from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class AgentState:
    last_update_id: int | None = None
    codex_thread_id: str | None = None
    session_turn_count: int = 0


class StateStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._state = self._read()

    def _read(self) -> AgentState:
        if not self.path.is_file():
            return AgentState()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"cannot read state file {self.path}: {exc}") from exc
        return AgentState(
            last_update_id=data.get("last_update_id"),
            codex_thread_id=data.get("codex_thread_id"),
            session_turn_count=data.get("session_turn_count", 0),
        )

    def snapshot(self) -> AgentState:
        with self._lock:
            return AgentState(**asdict(self._state))

    def set_last_update_id(self, update_id: int) -> None:
        with self._lock:
            self._state.last_update_id = update_id
            self._write()

    def set_codex_thread_id(self, thread_id: str | None) -> None:
        with self._lock:
            self._state.codex_thread_id = thread_id
            if thread_id is None:
                self._state.session_turn_count = 0
            self._write()

    def record_codex_turn(self, thread_id: str) -> None:
        with self._lock:
            if self._state.codex_thread_id != thread_id:
                self._state.codex_thread_id = thread_id
                self._state.session_turn_count = 0
            self._state.session_turn_count += 1
            self._write()

    def _write(self) -> None:
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(asdict(self._state), indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, self.path)
