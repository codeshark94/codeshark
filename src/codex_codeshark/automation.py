from __future__ import annotations

import re
import json
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from .secure_io import ensure_private_directory, ensure_private_file


TASK_STATUSES = {
    "awaiting_approval",
    "queued",
    "running",
    "completed",
    "failed",
    "cancelled",
    "rejected",
}
SCHEDULE_STATUSES = {"awaiting_approval", "enabled", "paused", "completed", "rejected"}


@dataclass(frozen=True)
class TaskRecord:
    id: str
    chat_id: int
    prompt: str
    source: str
    ephemeral: bool
    status: str
    created_at: float
    due_at: float
    attempts: int
    approved: bool
    restricted: bool
    requester_id: int | None
    reply_to_message_id: int | None


@dataclass(frozen=True)
class ScheduleRecord:
    id: str
    chat_id: int
    kind: str
    expression: str
    prompt: str
    status: str
    next_run_at: float
    created_at: float
    last_run_at: float | None
    approved: bool


@dataclass(frozen=True)
class DeliveryRecord:
    id: str
    chat_id: int
    text: str
    status: str
    attempts: int
    last_error: str
    created_at: float
    updated_at: float


@dataclass(frozen=True)
class TaskManifest:
    task_id: str
    project: str
    tier: str
    phase: str
    acceptance: tuple[str, ...]
    artifacts: tuple[str, ...]
    checks: tuple[str, ...]
    delivery_state: str
    updated_at: float


@dataclass(frozen=True)
class GuardrailCandidate:
    id: str
    source_task_id: str
    content: str
    status: str
    created_at: float


@dataclass(frozen=True)
class GroupChatRecord:
    chat_id: int
    title: str
    enabled_by: int
    enabled_at: float


class RiskPolicy:
    _PATTERN = re.compile(
        r"(?:\b(?:delete|remove|erase|alter|write|edit|modify|change|fix|implement|"
        r"refactor|rename|move|copy|overwrite|run|execute|build|install|start|restart|"
        r"stop|test|deploy|publish|post|send|email|pay|purchase|buy|merge|release|"
        r"upload|push)\b|삭제|제거|지워|수정|변경|고쳐|구현|리팩터|이동|복사|덮어쓰|"
        r"작성|실행|테스트|빌드|설치|시작|재시작|중지|배포|게시|발행|전송|메일|결제|구매|"
        r"병합|릴리스|업로드|푸시|"
        r"\b(?:create|close|comment|reply|invite)\b.{0,40}"
        r"\b(?:issue|pull request|event|message|email)\b|"
        r"(?:이슈|풀 리퀘스트|PR|일정|메시지|메일).{0,20}"
        r"(?:생성|만들|닫|댓글|답장|초대))",
        re.IGNORECASE,
    )

    _GROUP_ADMIN_PATTERN = re.compile(
        r"(?:\b(?:delete|remove|erase|overwrite|wipe|shred|truncate|rmdir|drop|format|purge)\b|"
        r"\brm\s+(?:-[A-Za-z]*r|--recursive)|\bgit\s+(?:reset\s+--hard|clean\s+-[A-Za-z]*f)|"
        r"삭제|제거|지워|덮어쓰|초기화|파기|"
        r"\b(?:install|uninstall)\b.{0,60}\b(?:dependency|package|plugin)|"
        r"\b(?:dependency|package|plugin)\b.{0,60}\b(?:install|uninstall)|"
        r"(?:의존성|패키지|플러그인).{0,30}(?:설치|제거)|"
        r"\b(?:read|show|reveal|export|use|access|list|change|modify|edit|disable|enable|bypass|override)\b"
        r".{0,60}\b(?:credential|credentials|secret|password|token|api[ _-]?key|auth(?:entication)?|"
        r"ssh|keychain|identity|permission|policy|sandbox|allowlist|administrator|admin|"
        r"workdir|workspace root|delegated root|read[ _-]?only root|codex[ _-]?home)\b|"
        r"(?:자격증명|비밀|비밀번호|토큰|API\s*키|인증|키체인|권한|정책|샌드박스|"
        r"관리자|루트).{0,30}(?:읽|보여|공개|내보내|사용|접근|변경|수정|비활성|활성|우회)|"
        r"\b(?:deploy|publish|release|push|merge|post|send|email|pay|purchase|buy)\b|"
        r"\b(?:create|close|comment|reply|invite)\b.{0,40}"
        r"\b(?:issue|pull request|event|message|email)\b|"
        r"(?:배포|게시|발행|릴리스|푸시|병합|전송|메일|결제|구매)|"
        r"(?:이슈|풀 리퀘스트|PR|일정|메시지|메일).{0,20}"
        r"(?:생성|만들|닫|댓글|답장|초대))",
        re.IGNORECASE,
    )

    def requires_approval(self, prompt: str) -> bool:
        return bool(self._PATTERN.search(prompt))

    def requires_group_admin_privileges(self, prompt: str) -> bool:
        return bool(self._GROUP_ADMIN_PATTERN.search(prompt))


def _parse_cron_field(value: str, minimum: int, maximum: int) -> tuple[set[int], bool]:
    if not value:
        raise ValueError("cron field must not be empty")
    wildcard = value == "*"
    result: set[int] = set()
    for item in value.split(","):
        base, separator, raw_step = item.partition("/")
        step = 1
        if separator:
            try:
                step = int(raw_step)
            except ValueError as exc:
                raise ValueError(f"invalid cron step: {item}") from exc
            if step <= 0:
                raise ValueError(f"invalid cron step: {item}")
        if base == "*":
            start, end = minimum, maximum
        elif "-" in base:
            raw_start, raw_end = base.split("-", 1)
            try:
                start, end = int(raw_start), int(raw_end)
            except ValueError as exc:
                raise ValueError(f"invalid cron range: {item}") from exc
        else:
            try:
                start = end = int(base)
            except ValueError as exc:
                raise ValueError(f"invalid cron value: {item}") from exc
        if start < minimum or end > maximum or start > end:
            raise ValueError(f"cron value out of range: {item}")
        result.update(range(start, end + 1, step))
    return result, wildcard


def next_cron_time(expression: str, after: datetime) -> datetime:
    fields = expression.split()
    if len(fields) != 5:
        raise ValueError("cron expression must have five fields")
    minutes, _ = _parse_cron_field(fields[0], 0, 59)
    hours, _ = _parse_cron_field(fields[1], 0, 23)
    days, days_wildcard = _parse_cron_field(fields[2], 1, 31)
    months, _ = _parse_cron_field(fields[3], 1, 12)
    weekdays, weekdays_wildcard = _parse_cron_field(fields[4], 0, 7)
    if 7 in weekdays:
        weekdays.remove(7)
        weekdays.add(0)

    candidate = after.replace(second=0, microsecond=0) + timedelta(minutes=1)
    for _ in range(366 * 24 * 60):
        cron_weekday = (candidate.weekday() + 1) % 7
        day_matches = candidate.day in days
        weekday_matches = cron_weekday in weekdays
        if days_wildcard:
            calendar_day_matches = weekday_matches
        elif weekdays_wildcard:
            calendar_day_matches = day_matches
        else:
            calendar_day_matches = day_matches or weekday_matches
        if (
            candidate.minute in minutes
            and candidate.hour in hours
            and candidate.month in months
            and calendar_day_matches
        ):
            return candidate
        candidate += timedelta(minutes=1)
    raise ValueError("cron expression has no run time within one year")


class AgentStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        ensure_private_directory(self.path.parent)
        ensure_private_file(self.path)
        self._initialize()
        ensure_private_file(self.path)

    def _connect(self) -> sqlite3.Connection:
        ensure_private_file(self.path)
        connection = sqlite3.connect(self.path, timeout=5)
        ensure_private_file(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    @staticmethod
    def _prune_tasks(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            DELETE FROM tasks
            WHERE status IN ('completed', 'failed', 'cancelled', 'rejected')
              AND id NOT IN (
                  SELECT id FROM tasks
                  WHERE status IN ('completed', 'failed', 'cancelled', 'rejected')
                  ORDER BY created_at DESC LIMIT 200
              )
            """
        )

    @staticmethod
    def _prune_schedules(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            DELETE FROM schedules
            WHERE status IN ('completed', 'rejected')
              AND id NOT IN (
                  SELECT id FROM schedules
                  WHERE status IN ('completed', 'rejected')
                  ORDER BY created_at DESC LIMIT 200
              )
            """
        )

    @staticmethod
    def _prune_deliveries(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            DELETE FROM deliveries
            WHERE status = 'sent'
              AND id NOT IN (
                  SELECT id FROM deliveries
                  WHERE status = 'sent'
                  ORDER BY updated_at DESC LIMIT 50
              )
            """
        )
        connection.execute(
            """
            DELETE FROM deliveries
            WHERE status = 'failed'
              AND id NOT IN (
                  SELECT id FROM deliveries
                  WHERE status = 'failed'
                  ORDER BY updated_at DESC LIMIT 100
              )
            """
        )

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    chat_id INTEGER NOT NULL,
                    prompt TEXT NOT NULL,
                    source TEXT NOT NULL,
                    ephemeral INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    due_at REAL NOT NULL,
                    started_at REAL,
                    finished_at REAL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    error TEXT NOT NULL DEFAULT '',
                    approved INTEGER NOT NULL DEFAULT 0,
                    restricted INTEGER NOT NULL DEFAULT 0,
                    requester_id INTEGER,
                    reply_to_message_id INTEGER
                );
                CREATE INDEX IF NOT EXISTS tasks_ready
                    ON tasks(status, due_at, created_at);
                CREATE TABLE IF NOT EXISTS schedules (
                    id TEXT PRIMARY KEY,
                    chat_id INTEGER NOT NULL,
                    kind TEXT NOT NULL,
                    expression TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    status TEXT NOT NULL,
                    next_run_at REAL NOT NULL,
                    created_at REAL NOT NULL,
                    last_run_at REAL,
                    approved INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS schedules_due
                    ON schedules(status, next_run_at);
                CREATE TABLE IF NOT EXISTS deliveries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 1,
                    last_error TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS deliveries_status
                    ON deliveries(status, updated_at);
                CREATE TABLE IF NOT EXISTS task_manifests (
                    task_id TEXT PRIMARY KEY,
                    project TEXT NOT NULL,
                    tier TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    acceptance_json TEXT NOT NULL DEFAULT '[]',
                    artifacts_json TEXT NOT NULL DEFAULT '[]',
                    checks_json TEXT NOT NULL DEFAULT '[]',
                    delivery_state TEXT NOT NULL DEFAULT 'not-requested',
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS artifact_receipts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT,
                    chat_id INTEGER NOT NULL,
                    path TEXT NOT NULL,
                    sha256 TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    error TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS artifact_receipts_task
                    ON artifact_receipts(task_id, created_at);
                CREATE TABLE IF NOT EXISTS guardrail_candidates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_task_id TEXT NOT NULL,
                    content TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS group_chats (
                    chat_id INTEGER PRIMARY KEY,
                    title TEXT NOT NULL,
                    enabled_by INTEGER NOT NULL,
                    enabled_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS group_context (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    request TEXT NOT NULL,
                    response TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS group_context_requester
                    ON group_context(chat_id, user_id, created_at);
                CREATE TABLE IF NOT EXISTS group_addressed_messages (
                    chat_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    created_at REAL NOT NULL,
                    PRIMARY KEY (chat_id, message_id)
                );
                CREATE INDEX IF NOT EXISTS group_addressed_messages_recent
                    ON group_addressed_messages(chat_id, created_at);
                """
            )
            task_columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(tasks)").fetchall()
            }
            if "approved" not in task_columns:
                connection.execute(
                    "ALTER TABLE tasks ADD COLUMN approved INTEGER NOT NULL DEFAULT 0"
                )
            if "restricted" not in task_columns:
                connection.execute(
                    "ALTER TABLE tasks ADD COLUMN restricted INTEGER NOT NULL DEFAULT 0"
                )
            if "requester_id" not in task_columns:
                connection.execute("ALTER TABLE tasks ADD COLUMN requester_id INTEGER")
            if "reply_to_message_id" not in task_columns:
                connection.execute("ALTER TABLE tasks ADD COLUMN reply_to_message_id INTEGER")
            schedule_columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(schedules)").fetchall()
            }
            if "approved" not in schedule_columns:
                connection.execute(
                    "ALTER TABLE schedules ADD COLUMN approved INTEGER NOT NULL DEFAULT 0"
                )
            self._prune_tasks(connection)
            self._prune_schedules(connection)
            self._prune_deliveries(connection)

    def recover_interrupted_tasks(self) -> None:
        """Return work interrupted by a gateway restart to its safe pending state."""
        with self._lock, self._connect() as connection:
            connection.execute(
                "UPDATE tasks SET status = 'awaiting_approval', started_at = NULL "
                "WHERE status = 'running' AND approved = 1"
            )
            connection.execute(
                "UPDATE tasks SET status = 'queued', started_at = NULL "
                "WHERE status = 'running' AND approved = 0"
            )

    @staticmethod
    def _task(row: sqlite3.Row | None) -> TaskRecord | None:
        if row is None:
            return None
        return TaskRecord(
            id=row["id"],
            chat_id=row["chat_id"],
            prompt=row["prompt"],
            source=row["source"],
            ephemeral=bool(row["ephemeral"]),
            status=row["status"],
            created_at=row["created_at"],
            due_at=row["due_at"],
            attempts=row["attempts"],
            approved=bool(row["approved"]),
            restricted=bool(row["restricted"]),
            requester_id=row["requester_id"],
            reply_to_message_id=row["reply_to_message_id"],
        )

    @staticmethod
    def _schedule(row: sqlite3.Row | None) -> ScheduleRecord | None:
        if row is None:
            return None
        return ScheduleRecord(
            id=row["id"],
            chat_id=row["chat_id"],
            kind=row["kind"],
            expression=row["expression"],
            prompt=row["prompt"],
            status=row["status"],
            next_run_at=row["next_run_at"],
            created_at=row["created_at"],
            last_run_at=row["last_run_at"],
            approved=bool(row["approved"]),
        )

    @staticmethod
    def _delivery(row: sqlite3.Row | None) -> DeliveryRecord | None:
        if row is None:
            return None
        return DeliveryRecord(
            id=f"d{row['id']}",
            chat_id=row["chat_id"],
            text=row["text"],
            status=row["status"],
            attempts=row["attempts"],
            last_error=row["last_error"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def record_delivery_failure(
        self,
        chat_id: int,
        text: str,
        error: str,
    ) -> DeliveryRecord:
        now = time.time()
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO deliveries
                    (chat_id, text, status, attempts, last_error, created_at, updated_at)
                VALUES (?, ?, 'failed', 1, ?, ?, ?)
                """,
                (chat_id, text[:3900], error[-500:], now, now),
            )
            self._prune_deliveries(connection)
            row = connection.execute(
                "SELECT * FROM deliveries WHERE id = ?",
                (cursor.lastrowid,),
            ).fetchone()
        return self._delivery(row)

    def get_delivery(self, delivery_id: str) -> DeliveryRecord | None:
        if not delivery_id.startswith("d") or not delivery_id[1:].isdigit():
            return None
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM deliveries WHERE id = ?",
                (int(delivery_id[1:]),),
            ).fetchone()
        return self._delivery(row)

    def list_failed_deliveries(self, limit: int = 20) -> list[DeliveryRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM deliveries WHERE status = 'failed' "
                "ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._delivery(row) for row in rows]

    def mark_delivery_attempt(self, delivery_id: str, error: str) -> bool:
        if not delivery_id.startswith("d") or not delivery_id[1:].isdigit():
            return False
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                "UPDATE deliveries SET attempts = attempts + 1, last_error = ?, "
                "updated_at = ? WHERE id = ? AND status = 'failed'",
                (error[-500:], time.time(), int(delivery_id[1:])),
            )
            return cursor.rowcount == 1

    def mark_delivery_sent(self, delivery_id: str) -> bool:
        if not delivery_id.startswith("d") or not delivery_id[1:].isdigit():
            return False
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                "UPDATE deliveries SET status = 'sent', text = '', last_error = '', "
                "updated_at = ? WHERE id = ? AND status = 'failed'",
                (time.time(), int(delivery_id[1:])),
            )
            self._prune_deliveries(connection)
            return cursor.rowcount == 1

    @staticmethod
    def _manifest(row: sqlite3.Row | None) -> TaskManifest | None:
        if row is None:
            return None
        return TaskManifest(
            task_id=row["task_id"],
            project=row["project"],
            tier=row["tier"],
            phase=row["phase"],
            acceptance=tuple(json.loads(row["acceptance_json"])),
            artifacts=tuple(json.loads(row["artifacts_json"])),
            checks=tuple(json.loads(row["checks_json"])),
            delivery_state=row["delivery_state"],
            updated_at=row["updated_at"],
        )

    def upsert_task_manifest(
        self,
        task_id: str,
        *,
        project: str,
        tier: str,
        phase: str,
        acceptance: tuple[str, ...] = (),
        artifacts: tuple[str, ...] = (),
        checks: tuple[str, ...] = (),
        delivery_state: str = "not-requested",
    ) -> None:
        now = time.time()
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO task_manifests
                    (task_id, project, tier, phase, acceptance_json, artifacts_json,
                     checks_json, delivery_state, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    phase = excluded.phase,
                    acceptance_json = excluded.acceptance_json,
                    artifacts_json = excluded.artifacts_json,
                    checks_json = excluded.checks_json,
                    delivery_state = excluded.delivery_state,
                    updated_at = excluded.updated_at
                """,
                (
                    task_id,
                    project,
                    tier,
                    phase,
                    json.dumps(acceptance),
                    json.dumps(artifacts),
                    json.dumps(checks),
                    delivery_state,
                    now,
                ),
            )

    def get_task_manifest(self, task_id: str) -> TaskManifest | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM task_manifests WHERE task_id = ?", (task_id,)
            ).fetchone()
        return self._manifest(row)

    def record_artifact_receipt(
        self,
        *,
        task_id: str | None,
        chat_id: int,
        path: str,
        sha256: str,
        size_bytes: int,
        status: str,
        error: str = "",
    ) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO artifact_receipts
                    (task_id, chat_id, path, sha256, size_bytes, status, error, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (task_id, chat_id, path, sha256, size_bytes, status, error[-500:], time.time()),
            )

    def propose_guardrail(self, source_task_id: str, content: str) -> GuardrailCandidate:
        normalized = " ".join(content.split())[:1000]
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO guardrail_candidates (source_task_id, content, created_at) VALUES (?, ?, ?)",
                (source_task_id, normalized, time.time()),
            )
            row = connection.execute(
                "SELECT * FROM guardrail_candidates WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
        return GuardrailCandidate(
            id=f"g{row['id']}", source_task_id=row["source_task_id"], content=row["content"],
            status=row["status"], created_at=row["created_at"],
        )

    def list_guardrails(self, limit: int = 20) -> list[GuardrailCandidate]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM guardrail_candidates ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [
            GuardrailCandidate(f"g{row['id']}", row["source_task_id"], row["content"], row["status"], row["created_at"])
            for row in rows
        ]

    def enqueue_task(
        self,
        chat_id: int,
        prompt: str,
        *,
        source: str,
        ephemeral: bool,
        requires_approval: bool = False,
        restricted: bool = False,
        requester_id: int | None = None,
        reply_to_message_id: int | None = None,
        due_at: float | None = None,
    ) -> TaskRecord:
        now = time.time()
        task_id = "t" + uuid.uuid4().hex[:10]
        status = "awaiting_approval" if requires_approval else "queued"
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO tasks
                    (id, chat_id, prompt, source, ephemeral, status, created_at, due_at,
                     restricted, requester_id, reply_to_message_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    chat_id,
                    prompt,
                    source,
                    int(ephemeral),
                    status,
                    now,
                    due_at or now,
                    int(restricted),
                    requester_id,
                    reply_to_message_id,
                ),
            )
        return self.get_task(task_id)

    def append_to_recent_queued_task(
        self,
        chat_id: int,
        prompt: str,
        *,
        window_seconds: int = 12,
    ) -> TaskRecord | None:
        cutoff = time.time() - window_seconds
        with self._lock, self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM tasks
                WHERE chat_id = ? AND source = 'telegram' AND status = 'queued'
                  AND ephemeral = 0 AND created_at >= ?
                ORDER BY created_at DESC LIMIT 1
                """,
                (chat_id, cutoff),
            ).fetchone()
            if row is None:
                return None
            combined = row["prompt"] + "\n\n[Additional user message]\n" + prompt
            connection.execute("UPDATE tasks SET prompt = ? WHERE id = ?", (combined, row["id"]))
            updated = connection.execute("SELECT * FROM tasks WHERE id = ?", (row["id"],)).fetchone()
        return self._task(updated)

    def claim_next_task(self, *, now: float | None = None) -> TaskRecord | None:
        current = time.time() if now is None else now
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT candidate.* FROM tasks AS candidate
                WHERE candidate.status = 'queued' AND candidate.due_at <= ?
                  AND NOT EXISTS (
                    SELECT 1 FROM tasks AS active
                    WHERE active.status = 'running'
                      AND active.chat_id = candidate.chat_id
                      AND (
                        active.ephemeral = 0
                        OR candidate.ephemeral = 0
                        OR (
                            active.restricted = 1
                            AND candidate.restricted = 1
                            AND active.requester_id = candidate.requester_id
                        )
                      )
                  )
                ORDER BY candidate.due_at, candidate.created_at LIMIT 1
                """,
                (current,),
            ).fetchone()
            if row is None:
                connection.commit()
                return None
            connection.execute(
                """
                UPDATE tasks
                SET status = 'running', started_at = ?, attempts = attempts + 1
                WHERE id = ?
                """,
                (current, row["id"]),
            )
            connection.commit()
        return self.get_task(row["id"])

    def get_task(self, task_id: str) -> TaskRecord | None:
        with self._connect() as connection:
            return self._task(connection.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone())

    def finish_task(
        self,
        task_id: str,
        status: str,
        error: str = "",
        *,
        attempt: int | None = None,
    ) -> bool:
        if status not in {"completed", "failed", "cancelled"}:
            raise ValueError("invalid terminal task status")
        attempt_clause = "AND attempts = ?" if attempt is not None else ""
        parameters: tuple[object, ...] = (status, time.time(), error[-1000:], task_id)
        if attempt is not None:
            parameters += (attempt,)
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                f"""
                UPDATE tasks
                SET status = ?, prompt = '', finished_at = ?, error = ?
                WHERE id = ? AND status = 'running'
                {attempt_clause}
                """,
                parameters,
            )
            self._prune_tasks(connection)
            return cursor.rowcount == 1

    def approve(self, item_id: str, *, now: float | None = None) -> bool:
        current = time.time() if now is None else now
        with self._lock, self._connect() as connection:
            if item_id.startswith("t"):
                cursor = connection.execute(
                    "UPDATE tasks SET status = 'queued', due_at = ?, approved = 1 "
                    "WHERE id = ? AND status = 'awaiting_approval'",
                    (current, item_id),
                )
            elif item_id.startswith("j"):
                cursor = connection.execute(
                    "UPDATE schedules SET status = 'enabled', "
                    "next_run_at = MAX(next_run_at, ?), approved = 1 "
                    "WHERE id = ? AND status = 'awaiting_approval'",
                    (current, item_id),
                )
            else:
                return False
            self._prune_tasks(connection)
            self._prune_schedules(connection)
            return cursor.rowcount == 1

    def reject(self, item_id: str) -> bool:
        with self._lock, self._connect() as connection:
            if item_id.startswith("t"):
                cursor = connection.execute(
                    "UPDATE tasks SET status = 'rejected', prompt = '' "
                    "WHERE id = ? AND status = 'awaiting_approval'",
                    (item_id,),
                )
            elif item_id.startswith("j"):
                cursor = connection.execute(
                    "UPDATE schedules SET status = 'rejected', prompt = '' "
                    "WHERE id = ? AND status = 'awaiting_approval'",
                    (item_id,),
                )
            else:
                return False
            return cursor.rowcount == 1

    def pending_count(self) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM tasks "
                "WHERE status IN ('awaiting_approval', 'queued', 'running')"
            ).fetchone()
            return int(row["count"])

    def restricted_pending_count(self) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM tasks "
                "WHERE restricted = 1 "
                "AND status IN ('awaiting_approval', 'queued', 'running')"
            ).fetchone()
            return int(row["count"])

    def enable_group(self, chat_id: int, title: str, enabled_by: int) -> GroupChatRecord:
        normalized_title = " ".join(title.split())[:200] or str(chat_id)
        now = time.time()
        with self._lock, self._connect() as connection:
            exists = connection.execute(
                "SELECT 1 FROM group_chats WHERE chat_id = ?",
                (chat_id,),
            ).fetchone()
            if exists is None:
                count = connection.execute(
                    "SELECT COUNT(*) AS count FROM group_chats"
                ).fetchone()["count"]
                if count >= 20:
                    raise ValueError("the enabled group limit of 20 has been reached")
            connection.execute(
                """
                INSERT INTO group_chats (chat_id, title, enabled_by, enabled_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(chat_id) DO UPDATE SET
                    title = excluded.title,
                    enabled_by = excluded.enabled_by,
                    enabled_at = excluded.enabled_at
                """,
                (chat_id, normalized_title, enabled_by, now),
            )
        return GroupChatRecord(chat_id, normalized_title, enabled_by, now)

    def disable_group(self, chat_id: int) -> bool:
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM group_chats WHERE chat_id = ?",
                (chat_id,),
            )
            connection.execute(
                "UPDATE tasks SET status = 'cancelled', prompt = '', finished_at = ? "
                "WHERE chat_id = ? AND restricted = 1 AND status = 'queued'",
                (time.time(), chat_id),
            )
            connection.execute("DELETE FROM group_context WHERE chat_id = ?", (chat_id,))
            connection.execute("DELETE FROM group_addressed_messages WHERE chat_id = ?", (chat_id,))
            return cursor.rowcount == 1

    def group_context(
        self,
        chat_id: int,
        user_id: int,
        *,
        limit: int = 6,
        now: float | None = None,
    ) -> list[tuple[str, str]]:
        cutoff = (time.time() if now is None else now) - 30 * 86400
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT request, response FROM group_context "
                "WHERE chat_id = ? AND user_id = ? AND created_at >= ? "
                "ORDER BY created_at DESC, id DESC LIMIT ?",
                (chat_id, user_id, cutoff, limit),
            ).fetchall()
        return [(row["request"], row["response"]) for row in reversed(rows)]

    def append_group_context(
        self,
        chat_id: int,
        user_id: int,
        request: str,
        response: str,
        *,
        now: float | None = None,
    ) -> None:
        normalized_request = request.strip()[:2000]
        normalized_response = response.strip()[:4000]
        if not normalized_request or not normalized_response:
            return
        created_at = time.time() if now is None else now
        with self._lock, self._connect() as connection:
            connection.execute(
                "INSERT INTO group_context "
                "(chat_id, user_id, request, response, created_at) VALUES (?, ?, ?, ?, ?)",
                (chat_id, user_id, normalized_request, normalized_response, created_at),
            )
            connection.execute(
                "DELETE FROM group_context WHERE chat_id = ? AND user_id = ? AND id NOT IN "
                "(SELECT id FROM group_context WHERE chat_id = ? AND user_id = ? "
                "ORDER BY created_at DESC, id DESC LIMIT 6)",
                (chat_id, user_id, chat_id, user_id),
            )
            connection.execute(
                "DELETE FROM group_context WHERE created_at < ?",
                (created_at - 30 * 86400,),
            )
            connection.execute(
                "DELETE FROM group_context WHERE id NOT IN "
                "(SELECT id FROM group_context ORDER BY created_at DESC, id DESC LIMIT 1000)"
            )

    def remember_group_addressed_message(
        self,
        chat_id: int,
        message_id: int,
        *,
        now: float | None = None,
    ) -> None:
        created_at = time.time() if now is None else now
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO group_addressed_messages (chat_id, message_id, created_at)
                VALUES (?, ?, ?)
                ON CONFLICT(chat_id, message_id) DO UPDATE SET
                    created_at = excluded.created_at
                """,
                (chat_id, message_id, created_at),
            )
            connection.execute(
                "DELETE FROM group_addressed_messages WHERE created_at < ?",
                (created_at - 30 * 86400,),
            )
            connection.execute(
                "DELETE FROM group_addressed_messages WHERE rowid NOT IN "
                "(SELECT rowid FROM group_addressed_messages "
                "ORDER BY created_at DESC, chat_id, message_id LIMIT 2000)"
            )

    def is_group_addressed_message(
        self,
        chat_id: int,
        message_id: int,
        *,
        now: float | None = None,
    ) -> bool:
        cutoff = (time.time() if now is None else now) - 30 * 86400
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM group_addressed_messages "
                "WHERE chat_id = ? AND message_id = ? AND created_at >= ?",
                (chat_id, message_id, cutoff),
            ).fetchone()
        return row is not None

    def is_group_enabled(self, chat_id: int) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM group_chats WHERE chat_id = ?",
                (chat_id,),
            ).fetchone()
        return row is not None

    def list_groups(self) -> list[GroupChatRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM group_chats ORDER BY enabled_at DESC"
            ).fetchall()
        return [
            GroupChatRecord(
                chat_id=row["chat_id"],
                title=row["title"],
                enabled_by=row["enabled_by"],
                enabled_at=row["enabled_at"],
            )
            for row in rows
        ]

    def list_tasks(self, limit: int = 10) -> list[TaskRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._task(row) for row in rows]

    def cancel_oldest_queued(self, *, chat_id: int | None = None) -> str | None:
        with self._lock, self._connect() as connection:
            if chat_id is None:
                row = connection.execute(
                    "SELECT id FROM tasks WHERE status = 'queued' ORDER BY created_at LIMIT 1"
                ).fetchone()
            else:
                row = connection.execute(
                    "SELECT id FROM tasks WHERE status = 'queued' AND chat_id = ? "
                    "ORDER BY created_at LIMIT 1",
                    (chat_id,),
                ).fetchone()
            if row is None:
                return None
            connection.execute(
                "UPDATE tasks SET status = 'cancelled', prompt = '', finished_at = ? WHERE id = ?",
                (time.time(), row["id"]),
            )
            self._prune_tasks(connection)
            return row["id"]

    def create_schedule(
        self,
        chat_id: int,
        *,
        kind: str,
        expression: str,
        prompt: str,
        next_run_at: float,
        requires_approval: bool = False,
    ) -> ScheduleRecord:
        if kind not in {"once", "interval", "cron", "heartbeat"}:
            raise ValueError("invalid schedule kind")
        schedule_id = "j" + uuid.uuid4().hex[:10]
        now = time.time()
        status = "awaiting_approval" if requires_approval else "enabled"
        with self._lock, self._connect() as connection:
            count = connection.execute(
                "SELECT COUNT(*) AS count FROM schedules "
                "WHERE status IN ('awaiting_approval', 'enabled', 'paused')"
            ).fetchone()["count"]
            if count >= 100:
                raise ValueError("active schedule limit reached")
            connection.execute(
                """
                INSERT INTO schedules
                    (id, chat_id, kind, expression, prompt, status, next_run_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (schedule_id, chat_id, kind, expression, prompt, status, next_run_at, now),
            )
        return self.get_schedule(schedule_id)

    def get_schedule(self, schedule_id: str) -> ScheduleRecord | None:
        with self._connect() as connection:
            return self._schedule(
                connection.execute("SELECT * FROM schedules WHERE id = ?", (schedule_id,)).fetchone()
            )

    def list_schedules(self) -> list[ScheduleRecord]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM schedules ORDER BY created_at DESC").fetchall()
        return [self._schedule(row) for row in rows]

    def set_schedule_status(self, schedule_id: str, status: str) -> bool:
        if status not in {"enabled", "paused"}:
            raise ValueError("invalid schedule status")
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                "UPDATE schedules SET status = ? WHERE id = ? AND status IN ('enabled', 'paused')",
                (status, schedule_id),
            )
            return cursor.rowcount == 1

    def delete_schedule(self, schedule_id: str) -> bool:
        with self._lock, self._connect() as connection:
            cursor = connection.execute("DELETE FROM schedules WHERE id = ?", (schedule_id,))
            return cursor.rowcount == 1

    def enqueue_due_schedules(self, *, now: float | None = None) -> int:
        current = time.time() if now is None else now
        created = 0
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                "SELECT * FROM schedules WHERE status = 'enabled' AND next_run_at <= ?",
                (current,),
            ).fetchall()
            for row in rows:
                if row["kind"] in {"interval", "heartbeat"}:
                    next_run = current + int(row["expression"])
                elif row["kind"] == "cron":
                    local_now = datetime.fromtimestamp(current).astimezone()
                    next_run = next_cron_time(row["expression"], local_now).timestamp()
                else:
                    next_run = None
                source = (
                    "reminder"
                    if row["kind"] == "once"
                    else f"{row['kind']}:{row['id']}"
                )
                if row["kind"] != "once":
                    active = connection.execute(
                        "SELECT 1 FROM tasks WHERE source = ? "
                        "AND status IN ('awaiting_approval', 'queued', 'running') LIMIT 1",
                        (source,),
                    ).fetchone()
                    if active is not None:
                        connection.execute(
                            "UPDATE schedules SET next_run_at = ? WHERE id = ?",
                            (next_run, row["id"]),
                        )
                        continue
                task_id = "t" + uuid.uuid4().hex[:10]
                connection.execute(
                    """
                    INSERT INTO tasks
                        (id, chat_id, prompt, source, ephemeral, status, created_at, due_at, approved)
                    VALUES (?, ?, ?, ?, 1, 'queued', ?, ?, ?)
                    """,
                    (
                        task_id,
                        row["chat_id"],
                        row["prompt"],
                        source,
                        current,
                        current,
                        row["approved"],
                    ),
                )
                if row["kind"] == "once":
                    connection.execute(
                        "UPDATE schedules SET status = 'completed', prompt = '', last_run_at = ? "
                        "WHERE id = ?",
                        (current, row["id"]),
                    )
                elif row["kind"] in {"interval", "heartbeat"}:
                    connection.execute(
                        "UPDATE schedules SET next_run_at = ?, last_run_at = ? WHERE id = ?",
                        (next_run, current, row["id"]),
                    )
                else:
                    connection.execute(
                        "UPDATE schedules SET next_run_at = ?, last_run_at = ? WHERE id = ?",
                        (next_run, current, row["id"]),
                    )
                created += 1
            self._prune_schedules(connection)
            connection.commit()
        return created
