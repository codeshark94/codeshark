from __future__ import annotations

import re
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path


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


class RiskPolicy:
    _PATTERN = re.compile(
        r"(?:\b(?:delete|remove|deploy|publish|post|send|email|pay|purchase|buy|"
        r"merge|release|upload|push)\b|삭제|제거|배포|게시|발행|전송|메일|결제|구매|"
        r"병합|릴리스|업로드|푸시|"
        r"\b(?:create|close|comment|reply|invite)\b.{0,40}"
        r"\b(?:issue|pull request|event|message|email)\b|"
        r"(?:이슈|풀 리퀘스트|PR|일정|메시지|메일).{0,20}"
        r"(?:생성|만들|닫|댓글|답장|초대))",
        re.IGNORECASE,
    )

    def requires_approval(self, prompt: str) -> bool:
        return bool(self._PATTERN.search(prompt))


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
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5)
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
                    approved INTEGER NOT NULL DEFAULT 0
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
                """
            )
            task_columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(tasks)").fetchall()
            }
            if "approved" not in task_columns:
                connection.execute(
                    "ALTER TABLE tasks ADD COLUMN approved INTEGER NOT NULL DEFAULT 0"
                )
            schedule_columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(schedules)").fetchall()
            }
            if "approved" not in schedule_columns:
                connection.execute(
                    "ALTER TABLE schedules ADD COLUMN approved INTEGER NOT NULL DEFAULT 0"
                )
            connection.execute(
                "UPDATE tasks SET status = 'awaiting_approval', started_at = NULL "
                "WHERE status = 'running' AND approved = 1"
            )
            connection.execute(
                "UPDATE tasks SET status = 'queued', started_at = NULL "
                "WHERE status = 'running' AND approved = 0"
            )
            self._prune_tasks(connection)
            self._prune_schedules(connection)
            self._prune_deliveries(connection)

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

    def enqueue_task(
        self,
        chat_id: int,
        prompt: str,
        *,
        source: str,
        ephemeral: bool,
        requires_approval: bool = False,
        due_at: float | None = None,
    ) -> TaskRecord:
        now = time.time()
        task_id = "t" + uuid.uuid4().hex[:10]
        status = "awaiting_approval" if requires_approval else "queued"
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO tasks
                    (id, chat_id, prompt, source, ephemeral, status, created_at, due_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (task_id, chat_id, prompt, source, int(ephemeral), status, now, due_at or now),
            )
        return self.get_task(task_id)

    def claim_next_task(self, *, now: float | None = None) -> TaskRecord | None:
        current = time.time() if now is None else now
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT * FROM tasks
                WHERE status = 'queued' AND due_at <= ?
                ORDER BY due_at, created_at LIMIT 1
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

    def finish_task(self, task_id: str, status: str, error: str = "") -> bool:
        if status not in {"completed", "failed", "cancelled"}:
            raise ValueError("invalid terminal task status")
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE tasks
                SET status = ?, prompt = '', finished_at = ?, error = ?
                WHERE id = ? AND status = 'running'
                """,
                (status, time.time(), error[-1000:], task_id),
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

    def list_tasks(self, limit: int = 10) -> list[TaskRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._task(row) for row in rows]

    def cancel_oldest_queued(self) -> str | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT id FROM tasks WHERE status = 'queued' ORDER BY created_at LIMIT 1"
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
