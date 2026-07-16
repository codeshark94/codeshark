from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, replace
from datetime import datetime

from .automation import AgentStore, RiskPolicy, TaskRecord, next_cron_time
from .codex_runner import CodexRunner, RunResult
from .config import Config
from .learning import LearningStore, SkillStore, extract_learning_candidate
from .memory import FeedbackStore, MemoryStore, compose_prompt
from .state import StateStore
from .telegram_api import TelegramAPI, TelegramError


LOGGER = logging.getLogger(__name__)

HELP_TEXT = """Codex-codeshark

일반 텍스트: 현재 Codex 세션에 작업 요청
/status: 실행 중 작업, 대기열, 세션 확인
/new: 현재 세션을 삭제하고 새 Codex 세션 시작
/remember 내용: 승인된 장기 메모리 즉시 저장
/memories, /forget ID: 장기 메모리 관리
/learn memory 내용: 메모리 후보 만들기
/learn skill 이름 | 절차: 스킬 후보 만들기
/learning, /approve ID, /reject ID: 학습·위험 작업 승인
/skills, /forget_skill ID: 승인된 스킬 관리
/tasks: 최근 영속 작업 상태
/remind 분 요청: 일회성 알림 작업
/cron 표현식 | 요청: 반복 cron 작업
/heartbeat 분 요청: 주기적 점검 작업
/jobs, /pause ID, /resume_job ID, /delete_job ID: 예약 작업 관리
/mcp: 서버별 MCP 도구 allowlist 확인
/good [메모], /bad [이유]: 직전 완료 작업 평가
/cancel: 현재 실행 또는 다음 대기 작업 취소
/help: 이 도움말

원격 파일 작업은 서버에 고정된 workspace 안에서만 실행됩니다."""


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
        self.store = AgentStore(database_path)
        self.risk_policy = RiskPolicy()
        self.runner = CodexRunner(
            binary=config.codex_binary,
            profile=config.codex_profile,
            workdir=config.workdir,
            timeout_seconds=config.task_timeout_seconds,
            mcp_known_servers=config.mcp_known_servers,
            mcp_allowed_tools=config.mcp_allowed_tools,
        )
        self._status_lock = threading.Lock()
        self._active_task: TaskRecord | None = None
        self._last_completed_task: CompletedTask | None = None
        self._wake_worker = threading.Event()

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
            self.api.send_message(chat_id, "현재는 텍스트 메시지만 지원합니다.")
            return
        text = text.strip()
        command_parts = text.split(maxsplit=1)
        command = command_parts[0].split("@", 1)[0].lower()
        argument = command_parts[1].strip() if len(command_parts) == 2 else ""

        if command in {"/start", "/help"}:
            self.api.send_message(chat_id, HELP_TEXT)
            return
        if command == "/status":
            self.api.send_message(chat_id, self._status_text())
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
            self.api.send_message(chat_id, self._mcp_text())
            return
        if command in {"/good", "/bad"}:
            self._record_feedback(chat_id, command.removeprefix("/"), argument)
            return
        if command == "/cancel":
            self._cancel(chat_id)
            return
        if command.startswith("/"):
            self.api.send_message(chat_id, "알 수 없는 명령입니다. /help를 확인하세요.")
            return

        self._enqueue_user_task(chat_id, text)

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
                try:
                    self.api.send_message(task.chat_id, "내부 오류로 작업이 중단됐습니다. 로그를 확인하세요.")
                except TelegramError:
                    LOGGER.exception("failed to report worker error")
            finally:
                with self._status_lock:
                    self._active_task = None

    def _execute_task(self, task: TaskRecord) -> RunResult:
        if not task.ephemeral:
            self._rotate_session_if_needed(task.chat_id)
        self.api.send_typing(task.chat_id)
        self.api.send_message(task.chat_id, "Codex 작업을 시작합니다.")
        selected_skills = self.skills.select(task.prompt)
        prompt, memory_ids, skill_ids = compose_prompt(
            task.prompt,
            self.memory.list(),
            selected_skills,
            external_action_approved=task.approved,
            task_id=task.id,
        )
        thread_id = None if task.ephemeral else self.state.snapshot().codex_thread_id
        result = self.runner.run(prompt, thread_id, ephemeral=task.ephemeral)
        successful = result.exit_code == 0 and not result.cancelled and not result.timed_out
        clean_message, proposed = extract_learning_candidate(result.message)
        if proposed and successful:
            try:
                candidate = self.learning.propose(
                    kind=proposed.kind,
                    title=proposed.title,
                    content=proposed.content,
                    source_task_id=task.id,
                )
            except ValueError as exc:
                self.api.send_message(task.chat_id, f"학습 후보를 보관하지 못했습니다: {exc}")
            else:
                self.api.send_message(
                    task.chat_id,
                    f"학습 후보 {candidate.id} ({candidate.kind})를 만들었습니다. "
                    f"/approve {candidate.id} 또는 /reject {candidate.id}",
                )
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

    def _rotate_session_if_needed(self, chat_id: int) -> None:
        snapshot = self.state.snapshot()
        if not snapshot.codex_thread_id or snapshot.session_turn_count < self.config.max_session_turns:
            return
        summary_prompt = (
            "현재 세션을 종료하기 전에 다음 세션에도 필요한 사실, 사용자 선호 또는 "
            "재사용 절차만 하나의 학습 후보로 요약하라. 반드시 learning_candidate "
            "프로토콜 형식으로만 답하고 일회성 내용은 제외하라."
        )
        result = self.runner.run(summary_prompt, snapshot.codex_thread_id)
        if result.exit_code != 0 or result.cancelled or result.timed_out:
            LOGGER.warning("session rotation summary failed; keeping current session")
            return
        clean, proposed = extract_learning_candidate(result.message)
        if proposed is None and clean:
            proposed_title = "자동 세션 요약"
            proposed_content = clean[:1000]
            proposed_kind = "memory"
        elif proposed is not None:
            proposed_title = proposed.title
            proposed_content = proposed.content
            proposed_kind = proposed.kind
        else:
            LOGGER.warning("session rotation produced no durable summary; keeping current session")
            return
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
            return
        self.state.set_codex_thread_id(None)
        self.api.send_message(
            chat_id,
            f"세션 용량 한도에 따라 자동 회전했습니다. 요약은 학습 후보 {candidate.id}로 보관했습니다.",
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
            self.api.send_message(chat_id, "작업이 취소됐습니다.")
            return
        if result.timed_out:
            self.api.send_message(chat_id, "작업 제한시간을 초과해 중단했습니다.")
            return
        if result.exit_code != 0:
            details = result.stderr[-1500:] if result.stderr else "상세 오류 없음"
            self.api.send_message(chat_id, f"Codex 실행 실패 (exit {result.exit_code})\n\n{details}")
            return
        response = result.message or "Codex가 텍스트 응답 없이 작업을 완료했습니다."
        self._send_chunks(chat_id, response)

    def _enqueue_user_task(self, chat_id: int, prompt: str) -> None:
        if self.store.pending_count() >= self.config.queue_size:
            self.api.send_message(chat_id, "대기열이 가득 찼습니다. 잠시 후 다시 시도하세요.")
            return
        requires_approval = self.risk_policy.requires_approval(prompt)
        task = self.store.enqueue_task(
            chat_id,
            prompt,
            source="telegram",
            ephemeral=False,
            requires_approval=requires_approval,
        )
        if requires_approval:
            self.api.send_message(
                chat_id,
                f"외부 변경 또는 위험 작업으로 분류했습니다. 실행: /approve {task.id}, 거절: /reject {task.id}",
            )
        else:
            self._wake_worker.set()
            self.api.send_message(chat_id, f"요청을 접수했습니다. 대기열: {self.store.pending_count()}")

    def _start_new_session(self, chat_id: int) -> None:
        with self._status_lock:
            active = self._active_task is not None
        if active:
            self.api.send_message(chat_id, "현재 작업 중입니다. 먼저 /cancel을 실행하세요.")
            return
        thread_id = self.state.snapshot().codex_thread_id
        if thread_id:
            try:
                self.runner.delete_session(thread_id)
            except Exception as exc:
                LOGGER.warning("failed to delete Codex session %s: %s", thread_id, exc)
                self.api.send_message(
                    chat_id,
                    "현재 Codex 세션을 삭제하지 못했습니다. 세션은 그대로 유지됩니다.",
                )
                return
        self.state.set_codex_thread_id(None)
        self.api.send_message(
            chat_id,
            "현재 Codex 세션을 삭제했습니다. 다음 요청부터 새 세션을 시작합니다.",
        )

    def _remember(self, chat_id: int, argument: str) -> None:
        if not argument:
            self.api.send_message(chat_id, "사용법: /remember 기억할 내용")
            return
        try:
            item = self.memory.add(argument)
        except ValueError as exc:
            self.api.send_message(chat_id, f"기억을 저장하지 못했습니다: {exc}")
            return
        self.api.send_message(chat_id, f"장기 메모리 {item.id}에 저장했습니다.")

    def _forget_memory(self, chat_id: int, argument: str) -> None:
        if not argument:
            self.api.send_message(chat_id, "사용법: /forget 메모리-ID")
        elif self.memory.forget(argument):
            self.api.send_message(chat_id, f"장기 메모리 {argument}을 삭제했습니다.")
        else:
            self.api.send_message(chat_id, f"장기 메모리 {argument}을 찾지 못했습니다.")

    def _learn(self, chat_id: int, argument: str) -> None:
        kind, separator, content = argument.partition(" ")
        if kind == "memory" and separator and content.strip():
            title = "사용자 제안 메모리"
            body = content.strip()
        elif kind == "skill" and separator and "|" in content:
            title, body = (part.strip() for part in content.split("|", 1))
            if not title or not body:
                self.api.send_message(chat_id, "사용법: /learn skill 이름 | 절차")
                return
        else:
            self.api.send_message(
                chat_id,
                "사용법: /learn memory 내용 또는 /learn skill 이름 | 절차",
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
            self.api.send_message(chat_id, f"학습 후보를 만들지 못했습니다: {exc}")
            return
        self.api.send_message(
            chat_id,
            f"학습 후보 {candidate.id}를 만들었습니다. /approve {candidate.id}로 반영하세요.",
        )

    def _approve(self, chat_id: int, item_id: str) -> None:
        if item_id.startswith("l"):
            candidate = self.learning.get(item_id)
            if candidate is None or candidate.status != "pending":
                self.api.send_message(chat_id, "승인할 학습 후보를 찾지 못했습니다.")
                return
            try:
                if candidate.kind == "memory":
                    self.memory.add(candidate.content)
                else:
                    self.skills.add(candidate.title, candidate.content)
            except ValueError as exc:
                self.api.send_message(chat_id, f"학습 후보를 반영하지 못했습니다: {exc}")
                return
            self.learning.set_status(item_id, "approved")
            self.api.send_message(chat_id, f"학습 후보 {item_id}를 승인해 반영했습니다.")
            return
        if self.store.approve(item_id):
            self._wake_worker.set()
            self.api.send_message(chat_id, f"{item_id}을 승인했습니다.")
        else:
            self.api.send_message(chat_id, "승인할 작업을 찾지 못했습니다.")

    def _reject(self, chat_id: int, item_id: str) -> None:
        if item_id.startswith("l"):
            changed = self.learning.set_status(item_id, "rejected")
        else:
            changed = self.store.reject(item_id)
        if changed:
            self.api.send_message(chat_id, f"{item_id}을 거절했습니다.")
        else:
            self.api.send_message(chat_id, "거절할 항목을 찾지 못했습니다.")

    def _forget_skill(self, chat_id: int, skill_id: str) -> None:
        if self.skills.forget(skill_id):
            self.api.send_message(chat_id, f"스킬 {skill_id}을 삭제했습니다.")
        else:
            self.api.send_message(chat_id, "삭제할 스킬을 찾지 못했습니다.")

    def _create_interval_job(self, chat_id: int, argument: str, *, kind: str) -> None:
        raw_minutes, separator, prompt = argument.partition(" ")
        try:
            minutes = int(raw_minutes)
        except ValueError:
            minutes = 0
        if not separator or not prompt.strip() or not 1 <= minutes <= 525_600:
            command = "/remind" if kind == "once" else "/heartbeat"
            self.api.send_message(chat_id, f"사용법: {command} 분 요청")
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
            self.api.send_message(chat_id, f"예약 작업을 만들지 못했습니다: {exc}")
            return
        if requires_approval:
            message = f"예약 작업 {schedule.id}은 승인이 필요합니다: /approve {schedule.id}"
        else:
            message = f"예약 작업 {schedule.id}을 만들었습니다."
        self._wake_worker.set()
        self.api.send_message(chat_id, message)

    def _create_cron_job(self, chat_id: int, argument: str) -> None:
        expression, separator, prompt = argument.partition("|")
        if not separator or not prompt.strip():
            self.api.send_message(chat_id, "사용법: /cron 분 시 일 월 요일 | 요청")
            return
        try:
            next_run = next_cron_time(expression.strip(), datetime.now().astimezone())
        except ValueError as exc:
            self.api.send_message(chat_id, f"cron 표현식 오류: {exc}")
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
            self.api.send_message(chat_id, f"cron 작업을 만들지 못했습니다: {exc}")
            return
        if requires_approval:
            message = f"cron 작업 {schedule.id}은 승인이 필요합니다: /approve {schedule.id}"
        else:
            message = f"cron 작업 {schedule.id}을 만들었습니다."
        self._wake_worker.set()
        self.api.send_message(chat_id, message)

    def _set_job_status(self, chat_id: int, job_id: str, status: str) -> None:
        if self.store.set_schedule_status(job_id, status):
            self._wake_worker.set()
            self.api.send_message(chat_id, f"예약 작업 {job_id} 상태를 {status}로 변경했습니다.")
        else:
            self.api.send_message(chat_id, "예약 작업을 찾지 못했거나 상태를 변경할 수 없습니다.")

    def _delete_job(self, chat_id: int, job_id: str) -> None:
        if self.store.delete_schedule(job_id):
            self.api.send_message(chat_id, f"예약 작업 {job_id}을 삭제했습니다.")
        else:
            self.api.send_message(chat_id, "삭제할 예약 작업을 찾지 못했습니다.")

    def _cancel(self, chat_id: int) -> None:
        if self.runner.cancel():
            self.api.send_message(chat_id, "현재 Codex 작업에 취소 신호를 보냈습니다.")
            return
        task_id = self.store.cancel_oldest_queued()
        if task_id:
            self.api.send_message(chat_id, f"대기 작업 {task_id}을 취소했습니다.")
        else:
            self.api.send_message(chat_id, "취소할 실행 또는 대기 작업이 없습니다.")

    def _record_feedback(self, chat_id: int, rating: str, note: str) -> None:
        with self._status_lock:
            if self._active_task is not None:
                message = "현재 작업이 끝난 뒤 평가해 주세요."
            elif self._last_completed_task is None:
                message = "평가할 완료 작업이 없습니다."
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
                    candidate = None
                    if note:
                        candidate = self.learning.propose(
                            kind="memory",
                            title="사용자 교정" if rating == "bad" else "사용자 확인",
                            content=note,
                            source_task_id=completed.id,
                        )
                except ValueError as exc:
                    message = f"평가를 저장하지 못했습니다: {exc}"
                else:
                    self._last_completed_task = None
                    message = "직전 완료 작업의 평가를 저장했습니다."
                    if candidate:
                        message += f" 학습 후보: {candidate.id}"
        self.api.send_message(chat_id, message)

    def _status_text(self) -> str:
        with self._status_lock:
            active = self._active_task is not None
        snapshot = self.state.snapshot()
        session_id = snapshot.codex_thread_id
        session = session_id[:12] + "…" if session_id else "없음"
        return "\n".join(
            [
                f"실행 중: {'예' if active else '아니오'}",
                f"영속 대기열: {self.store.pending_count()}",
                f"Codex 세션: {session}",
                f"세션 turn: {snapshot.session_turn_count}/{self.config.max_session_turns}",
                f"장기 메모리: {len(self.memory.list())}",
                f"승인된 스킬: {len(self.skills.list())}",
                f"학습 후보: {len(self.learning.list_pending())}",
                f"예약 작업: {len(self.store.list_schedules())}",
                f"작업 폴더: {self.config.workdir}",
            ]
        )

    def _memories_text(self) -> str:
        memories = self.memory.list()
        if not memories:
            return "저장된 장기 메모리가 없습니다."
        lines = [f"승인된 장기 메모리 ({sum(len(item.text) for item in memories)}/{self.config.memory_max_chars}자):"]
        lines.extend(f"{item.id}. {item.text}" for item in memories)
        return "\n".join(lines)

    def _learning_text(self) -> str:
        candidates = self.learning.list_pending()
        if not candidates:
            return "대기 중인 학습 후보가 없습니다."
        lines = ["대기 중인 학습 후보:"]
        for item in candidates:
            preview = " ".join(item.content.split())[:180]
            lines.append(f"{item.id} [{item.kind}] {item.title}\n  {preview}")
        lines.append("\n승인: /approve ID · 거절: /reject ID")
        return "\n".join(lines)

    def _skills_text(self) -> str:
        skills = self.skills.list()
        if not skills:
            return "승인된 스킬이 없습니다."
        lines = ["승인된 스킬:"]
        lines.extend(f"{item.id}. {item.name} — {item.description}" for item in skills)
        return "\n".join(lines)

    def _tasks_text(self) -> str:
        tasks = self.store.list_tasks()
        if not tasks:
            return "기록된 작업이 없습니다."
        lines = ["최근 작업:"]
        lines.extend(f"{item.id} [{item.status}] {item.source}" for item in tasks)
        return "\n".join(lines)

    def _jobs_text(self) -> str:
        schedules = self.store.list_schedules()
        if not schedules:
            return "예약 작업이 없습니다."
        lines = ["예약 작업:"]
        for item in schedules:
            next_run = datetime.fromtimestamp(item.next_run_at).astimezone().isoformat(timespec="minutes")
            lines.append(f"{item.id} [{item.status}/{item.kind}] 다음 실행 {next_run}")
        return "\n".join(lines)

    def _mcp_text(self) -> str:
        if not self.config.mcp_known_servers:
            return "게이트웨이에 등록된 MCP 서버가 없습니다."
        allowed = dict(self.config.mcp_allowed_tools)
        lines = ["MCP 실행 정책:"]
        for server in self.config.mcp_known_servers:
            tools = allowed.get(server)
            detail = ", ".join(tools) if tools else "비활성화"
            lines.append(f"- {server}: {detail}")
        return "\n".join(lines)

    def _send_chunks(self, chat_id: int, text: str) -> None:
        for chunk in split_message(text):
            self.api.send_message(chat_id, chunk)
