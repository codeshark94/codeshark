from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .projects import DEFAULT_PROJECT, normalize_project_name
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
    active_projects: dict[str, str] = field(default_factory=dict)
    project_sessions: dict[str, dict[str, SessionState]] = field(default_factory=dict)
    legacy_session: SessionState | None = None
    owner_onboarding_requested: bool = False


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
        active_projects = self._active_projects(data.get("active_projects"))
        project_sessions = self._project_sessions(data.get("project_sessions"))
        return AgentState(
            last_update_id=data.get("last_update_id"),
            chat_sessions=chat_sessions,
            active_projects=active_projects,
            project_sessions=project_sessions,
            legacy_session=legacy_session,
            owner_onboarding_requested=data.get("owner_onboarding_requested") is True,
        )

    @staticmethod
    def _active_projects(data: object) -> dict[str, str]:
        if not isinstance(data, dict):
            return {}
        projects: dict[str, str] = {}
        for chat_id, project in data.items():
            if not isinstance(chat_id, str) or not isinstance(project, str):
                continue
            try:
                projects[chat_id] = normalize_project_name(project)
            except ValueError:
                continue
        return projects

    def _project_sessions(self, data: object) -> dict[str, dict[str, SessionState]]:
        if not isinstance(data, dict):
            return {}
        sessions: dict[str, dict[str, SessionState]] = {}
        for chat_id, raw_projects in data.items():
            if not isinstance(chat_id, str) or not isinstance(raw_projects, dict):
                continue
            parsed: dict[str, SessionState] = {}
            for project, raw_session in raw_projects.items():
                if not isinstance(project, str) or not isinstance(raw_session, dict):
                    continue
                try:
                    parsed[normalize_project_name(project)] = self._session_state(raw_session)
                except ValueError:
                    continue
            if parsed:
                sessions[chat_id] = parsed
        return sessions

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
                active_projects=dict(self._state.active_projects),
                project_sessions={
                    chat_id: dict(projects)
                    for chat_id, projects in self._state.project_sessions.items()
                },
                legacy_session=self._state.legacy_session,
                owner_onboarding_requested=self._state.owner_onboarding_requested,
            )

    def set_last_update_id(self, update_id: int) -> None:
        with self._lock:
            self._state.last_update_id = update_id
            self._write()

    def owner_onboarding_requested(self) -> bool:
        with self._lock:
            return self._state.owner_onboarding_requested

    def mark_owner_onboarding_requested(self) -> None:
        with self._lock:
            if self._state.owner_onboarding_requested:
                return
            self._state.owner_onboarding_requested = True
            self._write()

    def clear_owner_onboarding_requested(self) -> None:
        with self._lock:
            self._state.owner_onboarding_requested = False
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

    def active_project(self, chat_id: int) -> str:
        with self._lock:
            return self._state.active_projects.get(str(chat_id), DEFAULT_PROJECT)

    def set_active_project(self, chat_id: int, project: str) -> str:
        normalized = normalize_project_name(project)
        with self._lock:
            self._state.active_projects[str(chat_id)] = normalized
            self._write()
        return normalized

    def session_snapshot(self, chat_id: int, project: str | None = None) -> SessionState:
        with self._lock:
            key = str(chat_id)
            if project is None:
                return self._state.chat_sessions.get(key, SessionState())
            normalized = normalize_project_name(project)
            stored = self._state.project_sessions.get(key, {}).get(normalized)
            if stored is not None:
                return stored
            if normalized == DEFAULT_PROJECT:
                return self._state.chat_sessions.get(key, SessionState())
            return SessionState()

    def set_session_thread_id(
        self,
        chat_id: int,
        thread_id: str | None,
        project: str | None = None,
    ) -> None:
        with self._lock:
            key = str(chat_id)
            if project is not None:
                normalized = normalize_project_name(project)
                sessions = self._state.project_sessions.setdefault(key, {})
                previous = sessions.get(
                    normalized,
                    self._state.chat_sessions.get(key, SessionState())
                    if normalized == DEFAULT_PROJECT
                    else SessionState(),
                )
                if thread_id is None:
                    sessions.pop(normalized, None)
                else:
                    sessions[normalized] = SessionState(
                        codex_thread_id=thread_id,
                        session_turn_count=previous.session_turn_count,
                    )
                if not sessions:
                    self._state.project_sessions.pop(key, None)
                if normalized == DEFAULT_PROJECT:
                    if thread_id is None:
                        self._state.chat_sessions.pop(key, None)
                    else:
                        self._state.chat_sessions[key] = sessions[normalized]
                self._write()
                return
            if thread_id is None:
                self._state.chat_sessions.pop(key, None)
            else:
                previous = self._state.chat_sessions.get(key, SessionState())
                self._state.chat_sessions[key] = SessionState(
                    codex_thread_id=thread_id,
                    session_turn_count=previous.session_turn_count,
                )
            self._write()

    def record_session_turn(
        self,
        chat_id: int,
        thread_id: str,
        project: str | None = None,
    ) -> None:
        with self._lock:
            key = str(chat_id)
            if project is not None:
                normalized = normalize_project_name(project)
                sessions = self._state.project_sessions.setdefault(key, {})
                previous = sessions.get(
                    normalized,
                    self._state.chat_sessions.get(key, SessionState())
                    if normalized == DEFAULT_PROJECT
                    else SessionState(),
                )
                turn_count = previous.session_turn_count if previous.codex_thread_id == thread_id else 0
                session = SessionState(
                    codex_thread_id=thread_id,
                    session_turn_count=turn_count + 1,
                )
                sessions[normalized] = session
                if normalized == DEFAULT_PROJECT:
                    self._state.chat_sessions[key] = session
                self._write()
                return
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
            "owner_onboarding_requested": self._state.owner_onboarding_requested,
            "chat_sessions": {
                chat_id: asdict(session)
                for chat_id, session in self._state.chat_sessions.items()
            },
            "active_projects": self._state.active_projects,
            "project_sessions": {
                chat_id: {
                    project: asdict(session)
                    for project, session in sessions.items()
                }
                for chat_id, sessions in self._state.project_sessions.items()
            },
        }
        if self._state.legacy_session is not None:
            data["legacy_session"] = asdict(self._state.legacy_session)
        atomic_write_text(self.path, json.dumps(data, indent=2) + "\n")
