from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from .automation import AgentStore, LocalConversationMessage
from .config import Config
from .projects import normalize_project_name
from .secure_io import atomic_write_bytes, read_private_bytes
from .state import StateStore

LOCAL_CONSOLE_CHAT_ID = 0
LOCAL_CONSOLE_SOURCE = "local"


@dataclass(frozen=True)
class LocalSubmission:
    task_id: str
    project: str
    attachments: tuple[Path, ...]


def _safe_attachment_name(name: str) -> str:
    basename = name.replace("\\", "/").rsplit("/", 1)[-1]
    cleaned = re.sub(r"[^\w.-]+", "-", basename, flags=re.UNICODE).strip(".-")
    return (cleaned or "attachment")[:120]


def _stage_attachment(source: Path, config: Config) -> Path:
    expanded = source.expanduser()
    if expanded.is_symlink() or not expanded.is_file():
        raise ValueError(f"attachment must be a regular file: {source}")
    payload = read_private_bytes(expanded, max_bytes=config.attachment_max_bytes)
    inbox = config.workdir / ".codeshark" / "inbox"
    destination = inbox / f"local-{uuid.uuid4().hex[:12]}-{_safe_attachment_name(expanded.name)}"
    atomic_write_bytes(destination, payload)
    return destination


def submit_local_request(
    config: Config,
    prompt: str,
    *,
    attachments: tuple[Path, ...] = (),
) -> LocalSubmission:
    request = prompt.strip()
    if len(request) > 12000:
        raise ValueError("local request must be at most 12000 characters")
    staged = tuple(_stage_attachment(path, config) for path in attachments)
    if not request and not staged:
        raise ValueError("enter a request or attach a file")
    if not request:
        request = "Inspect the attached workspace file and report the useful findings."
    if staged:
        request += "\n\n" + "\n".join(
            f"[Attached workspace file: {path}]" for path in staged
        )
    state = StateStore(config.state_path)
    store = AgentStore(config.state_path.parent / "agent.db")
    if store.pending_count() >= config.queue_size:
        raise RuntimeError("the task queue is full")
    project = normalize_project_name(state.active_project(LOCAL_CONSOLE_CHAT_ID))
    task = store.enqueue_task(
        LOCAL_CONSOLE_CHAT_ID,
        f"[[CODESHARK_PROJECT: {project}]]\n{request}",
        source=LOCAL_CONSOLE_SOURCE,
        ephemeral=False,
        approved=True,
    )
    store.append_local_message(
        "user",
        prompt.strip() or "Inspect the attached file.",
        task_id=task.id,
        attachments=tuple(str(path) for path in staged),
    )
    return LocalSubmission(task.id, project, staged)


def local_history(config: Config, *, limit: int = 100) -> list[LocalConversationMessage]:
    return AgentStore(config.state_path.parent / "agent.db").list_local_messages(limit=limit)
