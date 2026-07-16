from __future__ import annotations

import re
import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class RecallEntry:
    kind: str
    source_id: str
    title: str
    content: str
    source_task_id: str | None
    created_at: str
    use_count: int
    good_count: int
    bad_count: int
    last_used_at: float | None


class RecallStore:
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

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS recall_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    source_task_id TEXT,
                    created_at TEXT NOT NULL,
                    use_count INTEGER NOT NULL DEFAULT 0,
                    good_count INTEGER NOT NULL DEFAULT 0,
                    bad_count INTEGER NOT NULL DEFAULT 0,
                    last_used_at REAL,
                    UNIQUE(kind, source_id)
                )
                """
            )
            try:
                connection.executescript(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS recall_fts USING fts5(
                        title,
                        content,
                        content='recall_entries',
                        content_rowid='id'
                    );
                    CREATE TRIGGER IF NOT EXISTS recall_entries_ai AFTER INSERT ON recall_entries BEGIN
                        INSERT INTO recall_fts(rowid, title, content)
                        VALUES (new.id, new.title, new.content);
                    END;
                    CREATE TRIGGER IF NOT EXISTS recall_entries_ad AFTER DELETE ON recall_entries BEGIN
                        INSERT INTO recall_fts(recall_fts, rowid, title, content)
                        VALUES ('delete', old.id, old.title, old.content);
                    END;
                    CREATE TRIGGER IF NOT EXISTS recall_entries_au AFTER UPDATE OF title, content ON recall_entries BEGIN
                        INSERT INTO recall_fts(recall_fts, rowid, title, content)
                        VALUES ('delete', old.id, old.title, old.content);
                        INSERT INTO recall_fts(rowid, title, content)
                        VALUES (new.id, new.title, new.content);
                    END;
                    """
                )
                connection.execute("INSERT INTO recall_fts(recall_fts) VALUES ('rebuild')")
            except sqlite3.OperationalError:
                pass

    @staticmethod
    def _entry(row: sqlite3.Row) -> RecallEntry:
        return RecallEntry(
            kind=row["kind"],
            source_id=row["source_id"],
            title=row["title"],
            content=row["content"],
            source_task_id=row["source_task_id"],
            created_at=row["created_at"],
            use_count=row["use_count"],
            good_count=row["good_count"],
            bad_count=row["bad_count"],
            last_used_at=row["last_used_at"],
        )

    def upsert(
        self,
        *,
        kind: str,
        source_id: str,
        title: str,
        content: str,
        source_task_id: str | None,
        created_at: str | None = None,
    ) -> None:
        if kind not in {"memory", "skill"}:
            raise ValueError("recall kind must be memory or skill")
        normalized_title = " ".join(title.split())[:100]
        normalized_content = content.strip()
        if not source_id or not normalized_title or not normalized_content:
            raise ValueError("recall entries require an ID, title, and content")
        timestamp = created_at or datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO recall_entries
                    (kind, source_id, title, content, source_task_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(kind, source_id) DO UPDATE SET
                    title = excluded.title,
                    content = excluded.content,
                    source_task_id = COALESCE(excluded.source_task_id, recall_entries.source_task_id)
                """,
                (
                    kind,
                    source_id,
                    normalized_title,
                    normalized_content,
                    source_task_id,
                    timestamp,
                ),
            )

    def delete(self, kind: str, source_id: str) -> bool:
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM recall_entries WHERE kind = ? AND source_id = ?",
                (kind, source_id),
            )
            return cursor.rowcount == 1

    def search(self, query: str, limit: int = 10) -> list[RecallEntry]:
        tokens = re.findall(r"[0-9A-Za-z가-힣_+-]{2,}", query.lower())
        if not tokens:
            return []
        maximum = max(1, min(limit, 20))
        fts_query = " OR ".join(f'"{token.replace(chr(34), chr(34) * 2)}"*' for token in tokens[:10])
        with self._connect() as connection:
            try:
                rows = connection.execute(
                    """
                    SELECT entries.*
                    FROM recall_fts
                    JOIN recall_entries AS entries ON entries.id = recall_fts.rowid
                    WHERE recall_fts MATCH ?
                    ORDER BY bm25(recall_fts),
                             (entries.good_count - entries.bad_count) DESC,
                             entries.use_count DESC
                    LIMIT ?
                    """,
                    (fts_query, maximum),
                ).fetchall()
            except sqlite3.OperationalError:
                clauses = " OR ".join("lower(title || ' ' || content) LIKE ?" for _ in tokens[:10])
                values = [f"%{token}%" for token in tokens[:10]]
                rows = connection.execute(
                    f"SELECT * FROM recall_entries WHERE {clauses} "
                    "ORDER BY (good_count - bad_count) DESC, use_count DESC LIMIT ?",
                    (*values, maximum),
                ).fetchall()
        return [self._entry(row) for row in rows]

    def mark_used(self, kind: str, source_ids: tuple[str, ...]) -> None:
        if not source_ids:
            return
        now = time.time()
        with self._lock, self._connect() as connection:
            connection.executemany(
                "UPDATE recall_entries SET use_count = use_count + 1, last_used_at = ? "
                "WHERE kind = ? AND source_id = ?",
                [(now, kind, source_id) for source_id in source_ids],
            )

    def record_feedback(
        self,
        *,
        memory_ids: tuple[str, ...],
        skill_ids: tuple[str, ...],
        rating: str,
    ) -> None:
        if rating not in {"good", "bad"}:
            raise ValueError("rating must be good or bad")
        column = "good_count" if rating == "good" else "bad_count"
        with self._lock, self._connect() as connection:
            for kind, source_ids in (("memory", memory_ids), ("skill", skill_ids)):
                connection.executemany(
                    f"UPDATE recall_entries SET {column} = {column} + 1 "
                    "WHERE kind = ? AND source_id = ?",
                    [(kind, source_id) for source_id in source_ids],
                )

    def quality_scores(self, kind: str) -> dict[str, int]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT source_id, use_count, good_count, bad_count "
                "FROM recall_entries WHERE kind = ?",
                (kind,),
            ).fetchall()
        return {
            row["source_id"]: min(row["use_count"], 5)
            + row["good_count"] * 3
            - row["bad_count"] * 4
            for row in rows
        }

    def stats(self, kind: str, source_id: str) -> RecallEntry | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM recall_entries WHERE kind = ? AND source_id = ?",
                (kind, source_id),
            ).fetchone()
        return self._entry(row) if row is not None else None

    def stale_memories(self, *, days: int = 90, limit: int = 10) -> list[RecallEntry]:
        cutoff = time.time() - max(1, days) * 86_400
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM recall_entries
                WHERE kind = 'memory'
                  AND (last_used_at IS NULL OR last_used_at < ? OR bad_count > good_count)
                ORDER BY (bad_count > good_count) DESC,
                         last_used_at IS NOT NULL,
                         last_used_at,
                         created_at
                LIMIT ?
                """,
                (cutoff, max(1, min(limit, 20))),
            ).fetchall()
        return [self._entry(row) for row in rows]
