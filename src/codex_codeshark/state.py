from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .secure_io import (
    atomic_write_text,
    ensure_private_directory,
    ensure_private_file,
    read_private_text,
)


@dataclass(frozen=True)
class SessionState:
    codex_thread_id: str | None = None
    session_turn_count: int = 0


@dataclass
class AgentState:
    last_update_id: int | None = None
    chat_sessions: dict[str, SessionState] = field(default_factory=dict)
    legacy_session: SessionState | None = None


class StateStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        ensure_private_directory(self.path.parent)
        ensure_private_file(self.path)
        self._state = self._read()

    def _read(self) -> AgentState:
        if not self.path.is_file():
            return AgentState()
        try:
            data = json.loads(read_private_text(self.path, max_bytes=1_000_000))
        except (OSError, RuntimeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"cannot read state file {self.path}: {exc}") from exc
        raw_sessions = data.get("chat_sessions", {})
        chat_sessions: dict[str, SessionState] = {}
        if isinstance(raw_sessions, dict):
            for chat_id, raw_session in raw_sessions.items():
                if isinstance(chat_id, str) and isinstance(raw_session, dict):
                    chat_sessions[chat_id] = self._session_state(raw_session)
        raw_legacy = data.get("legacy_session")
        if isinstance(raw_legacy, dict):
            legacy_session = self._session_state(raw_legacy)
        elif data.get("codex_thread_id") is not None:
            legacy_session = self._session_state(data)
        else:
            legacy_session = None
        return AgentState(
            last_update_id=data.get("last_update_id"),
            chat_sessions=chat_sessions,
            legacy_session=legacy_session,
        )

    @staticmethod
    def _session_state(data: dict) -> SessionState:
        thread_id = data.get("codex_thread_id")
        turns = data.get("session_turn_count", 0)
        return SessionState(
            codex_thread_id=thread_id if isinstance(thread_id, str) else None,
            session_turn_count=turns if isinstance(turns, int) and not isinstance(turns, bool) else 0,
        )

    def snapshot(self) -> AgentState:
        with self._lock:
            return AgentState(
                last_update_id=self._state.last_update_id,
                chat_sessions=dict(self._state.chat_sessions),
                legacy_session=self._state.legacy_session,
            )

    def set_last_update_id(self, update_id: int) -> None:
        with self._lock:
            self._state.last_update_id = update_id
            self._write()

    def migrate_legacy_session(self, chat_id: int) -> bool:
        with self._lock:
            legacy = self._state.legacy_session
            if legacy is None:
                return False
            self._state.chat_sessions.setdefault(str(chat_id), legacy)
            self._state.legacy_session = None
            self._write()
            return True

    def session_snapshot(self, chat_id: int) -> SessionState:
        with self._lock:
            return self._state.chat_sessions.get(str(chat_id), SessionState())

    def set_session_thread_id(self, chat_id: int, thread_id: str | None) -> None:
        with self._lock:
            key = str(chat_id)
            if thread_id is None:
                self._state.chat_sessions.pop(key, None)
            else:
                previous = self._state.chat_sessions.get(key, SessionState())
                self._state.chat_sessions[key] = SessionState(
                    codex_thread_id=thread_id,
                    session_turn_count=previous.session_turn_count,
                )
            self._write()

    def record_session_turn(self, chat_id: int, thread_id: str) -> None:
        with self._lock:
            key = str(chat_id)
            previous = self._state.chat_sessions.get(key, SessionState())
            turn_count = previous.session_turn_count if previous.codex_thread_id == thread_id else 0
            self._state.chat_sessions[key] = SessionState(
                codex_thread_id=thread_id,
                session_turn_count=turn_count + 1,
            )
            self._write()

    def _write(self) -> None:
        data = {
            "last_update_id": self._state.last_update_id,
            "chat_sessions": {
                chat_id: asdict(session)
                for chat_id, session in self._state.chat_sessions.items()
            },
        }
        if self._state.legacy_session is not None:
            data["legacy_session"] = asdict(self._state.legacy_session)
        atomic_write_text(self.path, json.dumps(data, indent=2) + "\n")
