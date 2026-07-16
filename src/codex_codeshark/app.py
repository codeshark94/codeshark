from __future__ import annotations

import logging
import re
import threading
import time
import uuid
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path

from .automation import AgentStore, RiskPolicy, TaskRecord, next_cron_time
from .codex_runner import CodexRunner, RunResult
from .config import Config
from .learning import LearningStore, SkillStore, extract_learning_candidate
from .memory import FeedbackStore, MemoryStore, compose_prompt
from .recall import RecallStore
from .state import StateStore
from .telegram_api import TelegramAPI, TelegramError


LOGGER = logging.getLogger(__name__)

HELP_TEXT = """Codex-codeshark

Plain text: submit a task to the current Codex session
/status: show the active task, queue, and session
/new: delete the current session and start fresh
/remember TEXT: store an approved long-term memory
/memories, /forget ID: manage long-term memories
/recall QUERY: search approved memories and skills with provenance
/review_memories: review unused, stale, or poorly rated memories
/learn memory TEXT: propose a memory
/learn skill NAME | PROCEDURE: propose a reusable skill
/learning, /approve ID, /reject ID: review learning and risky work
/skills, /forget_skill ID: manage approved skills
/tasks: show recent persistent tasks
/deliveries, /retry_delivery ID: inspect or retry failed replies
/remind MINUTES REQUEST: create a one-time job
/cron EXPRESSION | REQUEST: create a recurring cron job
/heartbeat MINUTES REQUEST: create a periodic check
/jobs, /pause ID, /resume_job ID, /delete_job ID: manage scheduled jobs
/mcp: show the MCP server and tool allowlist
/good [NOTE], /bad [REASON]: rate the last completed task
/cancel: cancel the active task or next queued task
/help: show this message

Remote file operations are confined to the server-controlled workspace."""


@dataclass(frozen=True)
class CompletedTask:
    id: str
    thread_id: str | None
    memory_ids: tuple[str, ...]
    skill_ids: tuple[str, ...]
    prompt: str
    response: str


def split_message(text: str, limit: int = 3900) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break
        cut = remaining.rfind("\n", 0, limit)
        if cut < limit // 2:
            cut = remaining.rfind(" ", 0, limit)
        if cut < limit // 2:
            cut = limit
        chunks.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip()
    return chunks


class AgentApp:
    def __init__(self, config: Config, api: TelegramAPI) -> None:
        self.config = config
        self.api = api
        runtime_dir = config.state_path.parent
        database_path = runtime_dir / "agent.db"
        self.state = StateStore(config.state_path)
        self.memory = MemoryStore(
            runtime_dir / "memory.json",
            max_total_chars=config.memory_max_chars,
        )
        self.feedback = FeedbackStore(runtime_dir / "feedback.jsonl")
        self.learning = LearningStore(database_path)
        self.skills = SkillStore(runtime_dir / "skills")
        self.recall = RecallStore(database_path)
        self.store = AgentStore(database_path)
        self.risk_policy = RiskPolicy()
        self.runner = CodexRunner(
            binary=config.codex_binary,
            profile=config.codex_profile,
            workdir=config.workdir,
            timeout_seconds=config.task_timeout_seconds,
            mcp_known_servers=config.mcp_known_servers,
            mcp_allowed_tools=config.mcp_allowed_tools,
            network_access=config.codex_network_access,
        )
        self._status_lock = threading.Lock()
        self._active_task: TaskRecord | None = None
        self._last_completed_task: CompletedTask | None = None
        self._wake_worker = threading.Event()
        self._sync_recall_index()

    def run_forever(self) -> None:
        identity = self.api.get_me()
        self.api.delete_webhook(drop_pending_updates=False)
        self.api.set_commands()
        LOGGER.info("starting @%s", identity.get("username", "unknown"))
        threading.Thread(target=self._worker, name="codex-worker", daemon=True).start()

        while True:
            snapshot = self.state.snapshot()
            offset = snapshot.last_update_id + 1 if snapshot.last_update_id is not None else None
            try:
                updates = self.api.get_updates(offset=offset, timeout=self.config.poll_timeout_seconds)
                for update in updates:
                    update_id = update.get("update_id")
                    if isinstance(update_id, int):
                        self.state.set_last_update_id(update_id)
                    self._handle_update(update)
            except TelegramError as exc:
                LOGGER.warning("poll failed: %s", exc)
                time.sleep(3)

    def _handle_update(self, update: dict) -> None:
        message = update.get("message")
        if not isinstance(message, dict):
            return
        sender = message.get("from")
        chat = message.get("chat")
        if not isinstance(sender, dict) or not isinstance(chat, dict):
            return
        user_id = sender.get("id")
        chat_id = chat.get("id")
        if user_id not in self.config.allowed_user_ids:
            LOGGER.warning("ignored unauthorized Telegram user id=%s", user_id)
            return
        if chat.get("type") != "private" or not isinstance(chat_id, int):
            return

        text = message.get("text")
        if not isinstance(text, str) or not text.strip():
            if self._enqueue_attachment(chat_id, message):
                return
            self._send_message(chat_id, "Send text, a photo, or a document.")
            return
        text = text.strip()
        command_parts = text.split(maxsplit=1)
        command = command_parts[0].split("@", 1)[0].lower()
        argument = command_parts[1].strip() if len(command_parts) == 2 else ""

        if command in {"/start", "/help"}:
            self._send_message(chat_id, HELP_TEXT)
            return
        if command == "/status":
            self._send_message(chat_id, self._status_text())
            return
        if command == "/new":
            self._start_new_session(chat_id)
            return
        if command == "/remember":
            self._remember(chat_id, argument)
            return
        if command == "/memories":
            self._send_chunks(chat_id, self._memories_text())
            return
        if command == "/recall":
            self._send_chunks(chat_id, self._recall_text(argument))
            return
        if command in {"/review-memories", "/review_memories"}:
            self._send_chunks(chat_id, self._review_memories_text())
            return
        if command == "/forget":
            self._forget_memory(chat_id, argument)
            return
        if command == "/learn":
            self._learn(chat_id, argument)
            return
        if command == "/learning":
            self._send_chunks(chat_id, self._learning_text())
            return
        if command == "/approve":
            self._approve(chat_id, argument)
            return
        if command == "/reject":
            self._reject(chat_id, argument)
            return
        if command == "/skills":
            self._send_chunks(chat_id, self._skills_text())
            return
        if command in {"/forget-skill", "/forget_skill"}:
            self._forget_skill(chat_id, argument)
            return
        if command == "/tasks":
            self._send_chunks(chat_id, self._tasks_text())
            return
        if command == "/deliveries":
            self._send_chunks(chat_id, self._deliveries_text())
            return
        if command in {"/retry-delivery", "/retry_delivery"}:
            self._retry_delivery(chat_id, argument)
            return
        if command == "/remind":
            self._create_interval_job(chat_id, argument, kind="once")
            return
        if command == "/heartbeat":
            self._create_interval_job(chat_id, argument, kind="heartbeat")
            return
        if command == "/cron":
            self._create_cron_job(chat_id, argument)
            return
        if command == "/jobs":
            self._send_chunks(chat_id, self._jobs_text())
            return
        if command == "/pause":
            self._set_job_status(chat_id, argument, "paused")
            return
        if command in {"/resume-job", "/resume_job"}:
            self._set_job_status(chat_id, argument, "enabled")
            return
        if command in {"/delete-job", "/delete_job"}:
            self._delete_job(chat_id, argument)
            return
        if command == "/mcp":
            self._send_message(chat_id, self._mcp_text())
            return
        if command in {"/good", "/bad"}:
            self._record_feedback(chat_id, command.removeprefix("/"), argument)
            return
        if command == "/cancel":
            self._cancel(chat_id)
            return
        if command.startswith("/"):
            self._send_message(chat_id, "Unknown command. Use /help for the command list.")
            return

        self._enqueue_user_task(chat_id, text)

    @staticmethod
    def _safe_attachment_name(name: str, fallback: str) -> str:
        basename = name.replace("\\", "/").rsplit("/", 1)[-1]
        cleaned = re.sub(r"[^\w.-]+", "-", basename, flags=re.UNICODE).strip(".-")
        return (cleaned or fallback)[:120]

    def _enqueue_attachment(self, chat_id: int, message: dict) -> bool:
        attachment = message.get("document")
        fallback = "document.bin"
        if not isinstance(attachment, dict):
            photos = message.get("photo")
            if not isinstance(photos, list) or not photos:
                return False
            attachment = photos[-1]
            fallback = "photo.jpg"
        file_id = attachment.get("file_id")
        if not isinstance(file_id, str) or not file_id:
            self._send_message(chat_id, "Telegram did not provide a usable attachment ID.")
            return True
        reported_size = attachment.get("file_size")
        if isinstance(reported_size, int) and reported_size > self.config.attachment_max_bytes:
            self._send_message(
                chat_id,
                f"The attachment exceeds the {self.config.attachment_max_bytes}-byte limit.",
            )
            return True

        original_name = attachment.get("file_name")
        safe_name = self._safe_attachment_name(
            original_name if isinstance(original_name, str) else fallback,
            fallback,
        )
        inbox = self.config.workdir / "inbox"
        inbox.mkdir(parents=True, exist_ok=True)
        inbox.chmod(0o700)
        destination = inbox / f"{uuid.uuid4().hex[:12]}-{safe_name}"
        try:
            self.api.download_file(
                file_id,
                destination,
                max_bytes=self.config.attachment_max_bytes,
            )
        except TelegramError as exc:
            LOGGER.warning("attachment download failed: %s", exc)
            self._send_message(chat_id, "The attachment could not be downloaded safely.")
            return True

        self._prune_attachment_inbox(inbox)

        relative_path = destination.relative_to(self.config.workdir)
        caption = message.get("caption")
        request = caption.strip() if isinstance(caption, str) else ""
        if request:
            prompt = f"{request}\n\n[Attached workspace file: {relative_path}]"
        else:
            prompt = f"Inspect the attached workspace file and report your findings: {relative_path}"
        if not self._enqueue_user_task(chat_id, prompt):
            destination.unlink(missing_ok=True)
        return True

    @staticmethod
    def _prune_attachment_inbox(inbox: Path, limit: int = 50) -> None:
        managed = [
            path
            for path in inbox.iterdir()
            if path.is_file() and re.fullmatch(r"[0-9a-f]{12}-.+", path.name)
        ]
        managed.sort(key=lambda path: path.stat().st_mtime, reverse=True)
        for path in managed[limit:]:
            path.unlink(missing_ok=True)

    def _worker(self) -> None:
        while True:
            try:
                self.store.enqueue_due_schedules()
                task = self.store.claim_next_task()
            except Exception:
                LOGGER.exception("failed to claim persistent task")
                self._wake_worker.wait(1)
                self._wake_worker.clear()
                continue
            if task is None:
                self._wake_worker.wait(1)
                self._wake_worker.clear()
                continue
            with self._status_lock:
                self._active_task = task
            try:
                result = self._execute_task(task)
                if result.cancelled:
                    status = "cancelled"
                elif result.exit_code != 0 or result.timed_out:
                    status = "failed"
                else:
                    status = "completed"
                self.store.finish_task(task.id, status, result.stderr)
            except Exception as exc:
                with self._status_lock:
                    self._last_completed_task = None
                self.store.finish_task(task.id, "failed", str(exc))
                LOGGER.exception("worker failed")
                self._send_message(
                    task.chat_id,
                    "The task stopped because of an internal error. Check the local logs.",
                )
            finally:
                with self._status_lock:
                    self._active_task = None

    def _execute_task(self, task: TaskRecord) -> RunResult:
        rotation_notice = None
        if not task.ephemeral:
            rotation_notice = self._rotate_session_if_needed()
        selected_skills = self.skills.select(
            task.prompt,
            quality_scores=self.recall.quality_scores("skill"),
        )
        prompt, memory_ids, skill_ids = compose_prompt(
            task.prompt,
            self.memory.list(),
            selected_skills,
            external_action_approved=task.approved,
            task_id=task.id,
        )
        self.recall.mark_used("memory", memory_ids)
        self.recall.mark_used("skill", skill_ids)
        thread_id = None if task.ephemeral else self.state.snapshot().codex_thread_id
        result = self.runner.run(prompt, thread_id, ephemeral=task.ephemeral)
        successful = result.exit_code == 0 and not result.cancelled and not result.timed_out
        clean_message, proposed = extract_learning_candidate(result.message)
        learning_notice = None
        if proposed and successful:
            try:
                candidate = self.learning.propose(
                    kind=proposed.kind,
                    title=proposed.title,
                    content=proposed.content,
                    source_task_id=task.id,
                )
            except ValueError as exc:
                learning_notice = f"Could not store the learning proposal: {exc}"
            else:
                learning_notice = (
                    f"Created learning proposal {candidate.id} ({candidate.kind}). "
                    f"Use /approve {candidate.id} or /reject {candidate.id}."
                )
        notices = [item for item in (rotation_notice, learning_notice) if item]
        if clean_message and notices:
            clean_message += "\n\n" + "\n".join(notices)
        elif notices:
            clean_message = "\n".join(notices)
        result = replace(result, message=clean_message)
        self._deliver_result(task.chat_id, result, persist_session=not task.ephemeral)
        with self._status_lock:
            self._last_completed_task = (
                CompletedTask(
                    id=task.id,
                    thread_id=result.thread_id,
                    memory_ids=memory_ids,
                    skill_ids=skill_ids,
                    prompt=task.prompt,
                    response=clean_message,
                )
                if successful
                else None
            )
        return result

    def _rotate_session_if_needed(self) -> str | None:
        snapshot = self.state.snapshot()
        if not snapshot.codex_thread_id or snapshot.session_turn_count < self.config.max_session_turns:
            return None
        summary_prompt = (
            "Before ending this session, summarize only durable facts, user preferences, "
            "or reusable procedures needed in future sessions as one learning proposal. "
            "Respond only with the learning_candidate protocol and omit one-off details."
        )
        result = self.runner.run(summary_prompt, snapshot.codex_thread_id)
        if result.exit_code != 0 or result.cancelled or result.timed_out:
            LOGGER.warning("session rotation summary failed; keeping current session")
            return None
        clean, proposed = extract_learning_candidate(result.message)
        if proposed is None and clean:
            proposed_title = "Automatic session summary"
            proposed_content = clean[:1000]
            proposed_kind = "memory"
        elif proposed is not None:
            proposed_title = proposed.title
            proposed_content = proposed.content
            proposed_kind = proposed.kind
        else:
            LOGGER.warning("session rotation produced no durable summary; keeping current session")
            return None
        candidate = self.learning.propose(
            kind=proposed_kind,
            title=proposed_title,
            content=proposed_content,
            source_task_id=None,
        )
        try:
            self.runner.delete_session(snapshot.codex_thread_id)
        except Exception:
            LOGGER.exception("failed to delete session during automatic rotation")
            return None
        self.state.set_codex_thread_id(None)
        return (
            f"The session reached its capacity and was rotated. "
            f"Its durable summary is learning proposal {candidate.id}."
        )

    def _deliver_result(
        self,
        chat_id: int,
        result: RunResult,
        *,
        persist_session: bool,
    ) -> None:
        if persist_session and result.thread_id:
            self.state.record_codex_turn(result.thread_id)
        if result.cancelled:
            self._send_message(chat_id, "The task was cancelled.")
            return
        if result.timed_out:
            self._send_message(chat_id, "The task exceeded its time limit and was stopped.")
            return
        if result.exit_code != 0:
            details = result.stderr[-1500:] if result.stderr else "No error details were returned."
            self._send_message(chat_id, f"Codex failed (exit {result.exit_code})\n\n{details}")
            return
        response = result.message or "Codex completed the task without a text response."
        self._send_chunks(chat_id, response)

    def _enqueue_user_task(self, chat_id: int, prompt: str) -> bool:
        if self.store.pending_count() >= self.config.queue_size:
            self._send_message(chat_id, "The queue is full. Try again later.")
            return False
        requires_approval = self.risk_policy.requires_approval(prompt)
        task = self.store.enqueue_task(
            chat_id,
            prompt,
            source="telegram",
            ephemeral=False,
            requires_approval=requires_approval,
        )
        if requires_approval:
            self._send_message(
                chat_id,
                f"This request may change external state or perform a risky action. "
                f"Run /approve {task.id} to continue or /reject {task.id} to discard it.",
            )
        else:
            self._wake_worker.set()
        return True

    def _start_new_session(self, chat_id: int) -> None:
        with self._status_lock:
            active = self._active_task is not None
        if active:
            self._send_message(chat_id, "A task is running. Use /cancel before resetting the session.")
            return
        thread_id = self.state.snapshot().codex_thread_id
        if thread_id:
            try:
                self.runner.delete_session(thread_id)
            except Exception as exc:
                LOGGER.warning("failed to delete Codex session %s: %s", thread_id, exc)
                self._send_message(
                    chat_id,
                    "The current Codex session could not be deleted and was kept unchanged.",
                )
                return
        self.state.set_codex_thread_id(None)
        self._send_message(
            chat_id,
            "The current Codex session was deleted. The next request will start a new session.",
        )

    def _remember(self, chat_id: int, argument: str) -> None:
        if not argument:
            self._send_message(chat_id, "Usage: /remember TEXT")
            return
        try:
            item = self.memory.add(argument)
        except ValueError as exc:
            self._send_message(chat_id, f"Could not store the memory: {exc}")
            return
        self.recall.upsert(
            kind="memory",
            source_id=item.id,
            title="User memory",
            content=item.text,
            source_task_id=None,
            created_at=item.created_at,
        )
        self._send_message(chat_id, f"Stored long-term memory {item.id}.")

    def _forget_memory(self, chat_id: int, argument: str) -> None:
        if not argument:
            self._send_message(chat_id, "Usage: /forget MEMORY_ID")
        elif self.memory.forget(argument):
            self.recall.delete("memory", argument)
            self._send_message(chat_id, f"Deleted long-term memory {argument}.")
        else:
            self._send_message(chat_id, f"Long-term memory {argument} was not found.")

    def _learn(self, chat_id: int, argument: str) -> None:
        kind, separator, content = argument.partition(" ")
        if kind == "memory" and separator and content.strip():
            title = "User-proposed memory"
            body = content.strip()
        elif kind == "skill" and separator and "|" in content:
            title, body = (part.strip() for part in content.split("|", 1))
            if not title or not body:
                self._send_message(chat_id, "Usage: /learn skill NAME | PROCEDURE")
                return
        else:
            self._send_message(
                chat_id,
                "Usage: /learn memory TEXT or /learn skill NAME | PROCEDURE",
            )
            return
        try:
            candidate = self.learning.propose(
                kind=kind,
                title=title,
                content=body,
                source_task_id=None,
            )
        except ValueError as exc:
            self._send_message(chat_id, f"Could not create the learning proposal: {exc}")
            return
        self._send_message(
            chat_id,
            f"Created learning proposal {candidate.id}. Use /approve {candidate.id} to apply it.",
        )

    def _approve(self, chat_id: int, item_id: str) -> None:
        if item_id.startswith("l"):
            candidate = self.learning.get(item_id)
            if candidate is None or candidate.status != "pending":
                self._send_message(chat_id, "No pending learning proposal was found for that ID.")
                return
            try:
                if candidate.kind == "memory":
                    item = self.memory.add(candidate.content)
                    self.recall.upsert(
                        kind="memory",
                        source_id=item.id,
                        title=candidate.title,
                        content=item.text,
                        source_task_id=candidate.source_task_id,
                        created_at=item.created_at,
                    )
                else:
                    item = self.skills.add(candidate.title, candidate.content)
                    self.recall.upsert(
                        kind="skill",
                        source_id=item.id,
                        title=item.name,
                        content=self.skills.read(item),
                        source_task_id=candidate.source_task_id,
                        created_at=item.created_at,
                    )
            except ValueError as exc:
                self._send_message(chat_id, f"Could not apply the learning proposal: {exc}")
                return
            self.learning.set_status(item_id, "approved")
            self._send_message(chat_id, f"Approved and applied learning proposal {item_id}.")
            return
        if self.store.approve(item_id):
            self._wake_worker.set()
            self._send_message(chat_id, f"Approved {item_id}.")
        else:
            self._send_message(chat_id, "No pending task or job was found for that ID.")

    def _reject(self, chat_id: int, item_id: str) -> None:
        if item_id.startswith("l"):
            changed = self.learning.set_status(item_id, "rejected")
        else:
            changed = self.store.reject(item_id)
        if changed:
            self._send_message(chat_id, f"Rejected {item_id}.")
        else:
            self._send_message(chat_id, "No pending item was found for that ID.")

    def _forget_skill(self, chat_id: int, skill_id: str) -> None:
        if self.skills.forget(skill_id):
            self.recall.delete("skill", skill_id)
            self._send_message(chat_id, f"Deleted skill {skill_id}.")
        else:
            self._send_message(chat_id, "No skill was found for that ID.")

    def _create_interval_job(self, chat_id: int, argument: str, *, kind: str) -> None:
        raw_minutes, separator, prompt = argument.partition(" ")
        try:
            minutes = int(raw_minutes)
        except ValueError:
            minutes = 0
        if not separator or not prompt.strip() or not 1 <= minutes <= 525_600:
            command = "/remind" if kind == "once" else "/heartbeat"
            self._send_message(chat_id, f"Usage: {command} MINUTES REQUEST")
            return
        requires_approval = self.risk_policy.requires_approval(prompt)
        try:
            schedule = self.store.create_schedule(
                chat_id,
                kind=kind,
                expression="" if kind == "once" else str(minutes * 60),
                prompt=prompt.strip(),
                next_run_at=time.time() + minutes * 60,
                requires_approval=requires_approval,
            )
        except ValueError as exc:
            self._send_message(chat_id, f"Could not create the scheduled job: {exc}")
            return
        if requires_approval:
            message = f"Scheduled job {schedule.id} requires approval: /approve {schedule.id}"
        else:
            message = f"Created scheduled job {schedule.id}."
        self._wake_worker.set()
        self._send_message(chat_id, message)

    def _create_cron_job(self, chat_id: int, argument: str) -> None:
        expression, separator, prompt = argument.partition("|")
        if not separator or not prompt.strip():
            self._send_message(chat_id, "Usage: /cron MIN HOUR DAY MONTH WEEKDAY | REQUEST")
            return
        try:
            next_run = next_cron_time(expression.strip(), datetime.now().astimezone())
        except ValueError as exc:
            self._send_message(chat_id, f"Invalid cron expression: {exc}")
            return
        requires_approval = self.risk_policy.requires_approval(prompt)
        try:
            schedule = self.store.create_schedule(
                chat_id,
                kind="cron",
                expression=expression.strip(),
                prompt=prompt.strip(),
                next_run_at=next_run.timestamp(),
                requires_approval=requires_approval,
            )
        except ValueError as exc:
            self._send_message(chat_id, f"Could not create the cron job: {exc}")
            return
        if requires_approval:
            message = f"Cron job {schedule.id} requires approval: /approve {schedule.id}"
        else:
            message = f"Created cron job {schedule.id}."
        self._wake_worker.set()
        self._send_message(chat_id, message)

    def _set_job_status(self, chat_id: int, job_id: str, status: str) -> None:
        if self.store.set_schedule_status(job_id, status):
            self._wake_worker.set()
            self._send_message(chat_id, f"Changed scheduled job {job_id} to {status}.")
        else:
            self._send_message(chat_id, "The scheduled job was not found or cannot change state.")

    def _delete_job(self, chat_id: int, job_id: str) -> None:
        if self.store.delete_schedule(job_id):
            self._send_message(chat_id, f"Deleted scheduled job {job_id}.")
        else:
            self._send_message(chat_id, "No scheduled job was found for that ID.")

    def _cancel(self, chat_id: int) -> None:
        if self.runner.cancel():
            self._send_message(chat_id, "Sent a cancellation signal to the active Codex task.")
            return
        task_id = self.store.cancel_oldest_queued()
        if task_id:
            self._send_message(chat_id, f"Cancelled queued task {task_id}.")
        else:
            self._send_message(chat_id, "There is no active or queued task to cancel.")

    def _record_feedback(self, chat_id: int, rating: str, note: str) -> None:
        with self._status_lock:
            if self._active_task is not None:
                message = "Wait for the active task to finish before rating it."
            elif self._last_completed_task is None:
                message = "There is no completed task available to rate."
            else:
                completed = self._last_completed_task
                try:
                    self.feedback.record(
                        task_id=completed.id,
                        rating=rating,
                        note=note,
                        thread_id=completed.thread_id,
                        memory_ids=completed.memory_ids,
                        skill_ids=completed.skill_ids,
                    )
                    self.recall.record_feedback(
                        memory_ids=completed.memory_ids,
                        skill_ids=completed.skill_ids,
                        rating=rating,
                    )
                    candidate = None
                    if note:
                        candidate = self.learning.propose(
                            kind="memory",
                            title="User correction" if rating == "bad" else "User confirmation",
                            content=note,
                            source_task_id=completed.id,
                        )
                except ValueError as exc:
                    message = f"Could not store the rating: {exc}"
                else:
                    self._last_completed_task = None
                    message = "Stored the rating for the last completed task."
                    if candidate:
                        message += f" Learning proposal: {candidate.id}."
        self._send_message(chat_id, message)

    def _status_text(self) -> str:
        with self._status_lock:
            active = self._active_task is not None
        snapshot = self.state.snapshot()
        session_id = snapshot.codex_thread_id
        session = session_id[:12] + "…" if session_id else "none"
        return "\n".join(
            [
                f"Active task: {'yes' if active else 'no'}",
                f"Persistent queue: {self.store.pending_count()}",
                f"Codex session: {session}",
                f"Session turns: {snapshot.session_turn_count}/{self.config.max_session_turns}",
                f"Long-term memories: {len(self.memory.list())}",
                f"Approved skills: {len(self.skills.list())}",
                f"Learning proposals: {len(self.learning.list_pending())}",
                f"Scheduled jobs: {len(self.store.list_schedules())}",
                f"Failed deliveries: {len(self.store.list_failed_deliveries())}",
                f"Codex network access: {'enabled' if self.config.codex_network_access else 'disabled'}",
                f"Workspace: {self.config.workdir}",
            ]
        )

    def _memories_text(self) -> str:
        memories = self.memory.list()
        if not memories:
            return "No long-term memories are stored."
        lines = [
            "Approved long-term memories "
            f"({sum(len(item.text) for item in memories)}/{self.config.memory_max_chars} chars):"
        ]
        for item in memories:
            stats = self.recall.stats("memory", item.id)
            usage = (
                f"uses={stats.use_count}, good={stats.good_count}, bad={stats.bad_count}"
                if stats
                else "not indexed"
            )
            lines.append(f"{item.id}. {item.text}\n  {usage}")
        return "\n".join(lines)

    def _recall_text(self, query: str) -> str:
        if not query:
            return "Usage: /recall QUERY"
        matches = self.recall.search(query)
        if not matches:
            return "No approved memories or skills matched that query."
        lines = [f'Recall results for "{query}":']
        for item in matches:
            preview = " ".join(item.content.split())[:300]
            provenance = f"source={item.source_id}"
            if item.source_task_id:
                provenance += f", task={item.source_task_id}"
            lines.append(
                f"[{item.kind}] {item.title} ({provenance})\n"
                f"  {preview}\n"
                f"  uses={item.use_count}, good={item.good_count}, bad={item.bad_count}"
            )
        return "\n".join(lines)

    def _review_memories_text(self) -> str:
        memories = self.recall.stale_memories()
        if not memories:
            return "No memories currently need review."
        lines = ["Memories to review:"]
        for item in memories:
            if item.bad_count > item.good_count:
                reason = "negative feedback exceeds positive feedback"
            elif item.last_used_at is None:
                reason = "never used"
            else:
                reason = "not used in at least 90 days"
            lines.append(f"{item.source_id}. {item.title} — {reason} (/forget {item.source_id})")
        return "\n".join(lines)

    def _learning_text(self) -> str:
        candidates = self.learning.list_pending()
        if not candidates:
            return "There are no pending learning proposals."
        lines = ["Pending learning proposals:"]
        for item in candidates:
            preview = " ".join(item.content.split())[:180]
            lines.append(f"{item.id} [{item.kind}] {item.title}\n  {preview}")
        lines.append("\nApprove: /approve ID · Reject: /reject ID")
        return "\n".join(lines)

    def _skills_text(self) -> str:
        skills = self.skills.list()
        if not skills:
            return "There are no approved skills."
        lines = ["Approved skills:"]
        for item in skills:
            stats = self.recall.stats("skill", item.id)
            usage = (
                f"uses={stats.use_count}, good={stats.good_count}, bad={stats.bad_count}"
                if stats
                else "not indexed"
            )
            lines.append(f"{item.id}. {item.name} — {item.description}\n  {usage}")
        return "\n".join(lines)

    def _sync_recall_index(self) -> None:
        for item in self.memory.list():
            if self.recall.stats("memory", item.id) is not None:
                continue
            self.recall.upsert(
                kind="memory",
                source_id=item.id,
                title="Approved memory",
                content=item.text,
                source_task_id=None,
                created_at=item.created_at,
            )
        for item in self.skills.list():
            if self.recall.stats("skill", item.id) is not None:
                continue
            self.recall.upsert(
                kind="skill",
                source_id=item.id,
                title=item.name,
                content=self.skills.read(item),
                source_task_id=None,
                created_at=item.created_at,
            )

    def _tasks_text(self) -> str:
        tasks = self.store.list_tasks()
        if not tasks:
            return "There are no recorded tasks."
        lines = ["Recent tasks:"]
        lines.extend(f"{item.id} [{item.status}] {item.source}" for item in tasks)
        return "\n".join(lines)

    def _deliveries_text(self) -> str:
        deliveries = self.store.list_failed_deliveries()
        if not deliveries:
            return "There are no failed Telegram deliveries."
        lines = ["Failed Telegram deliveries:"]
        for item in deliveries:
            preview = " ".join(item.text.split())[:120]
            lines.append(
                f"{item.id} [attempts={item.attempts}] {preview}\n"
                f"  {item.last_error[:180]}"
            )
        lines.append("\nRetry explicitly with /retry_delivery ID.")
        return "\n".join(lines)

    def _retry_delivery(self, chat_id: int, delivery_id: str) -> None:
        delivery = self.store.get_delivery(delivery_id)
        if delivery is None or delivery.status != "failed":
            self._send_message(chat_id, "No failed delivery was found for that ID.")
            return
        try:
            self.api.send_message(delivery.chat_id, delivery.text)
        except TelegramError as exc:
            self.store.mark_delivery_attempt(delivery.id, str(exc))
            self._send_message(chat_id, f"Delivery {delivery.id} is still failing: {exc}")
            return
        self.store.mark_delivery_sent(delivery.id)
        self._send_message(chat_id, f"Retried delivery {delivery.id} successfully.")

    def _jobs_text(self) -> str:
        schedules = self.store.list_schedules()
        if not schedules:
            return "There are no scheduled jobs."
        lines = ["Scheduled jobs:"]
        for item in schedules:
            next_run = datetime.fromtimestamp(item.next_run_at).astimezone().isoformat(timespec="minutes")
            lines.append(f"{item.id} [{item.status}/{item.kind}] next run {next_run}")
        return "\n".join(lines)

    def _mcp_text(self) -> str:
        if not self.config.mcp_known_servers:
            return "No MCP servers are registered with this gateway."
        allowed = dict(self.config.mcp_allowed_tools)
        lines = ["MCP execution policy:"]
        for server in self.config.mcp_known_servers:
            tools = allowed.get(server)
            detail = ", ".join(tools) if tools else "disabled"
            lines.append(f"- {server}: {detail}")
        return "\n".join(lines)

    def _send_chunks(self, chat_id: int, text: str) -> None:
        for chunk in split_message(text):
            self._send_message(chat_id, chunk)

    def _send_message(self, chat_id: int, text: str) -> bool:
        try:
            self.api.send_message(chat_id, text)
        except TelegramError as exc:
            delivery = self.store.record_delivery_failure(chat_id, text, str(exc))
            LOGGER.warning(
                "stored failed Telegram delivery %s (ambiguous=%s): %s",
                delivery.id,
                exc.ambiguous_delivery,
                exc,
            )
            return False
        return True
