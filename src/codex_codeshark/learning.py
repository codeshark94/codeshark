from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import threading
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class ProposedLearning:
    kind: str
    title: str
    content: str


@dataclass(frozen=True)
class LearningCandidate:
    id: str
    kind: str
    title: str
    content: str
    status: str
    source_task_id: str | None
    created_at: str


@dataclass(frozen=True)
class SkillRecord:
    id: str
    name: str
    description: str
    path: str
    created_at: str
    content: str = ""


LEARNING_PROTOCOL = """
[Automatic learning protocol]
At the end of every authenticated administrator task, proactively and independently decide whether the current conversation and accumulated context contain an explicit or repeated user preference, stable working pattern, durable personal or project fact, or reusable procedure that will improve future work. This decision does not require a /learn command or a request from the user. Ignore one-off details, guesses, secrets, credentials, and sensitive data that is not needed for future tasks.
When there is a high-value durable pattern, append exactly one block in the following format to the end of the final response. Use the same stable title when updating an existing pattern. To improve an existing skill, use the same title and provide the complete replacement procedure.
<learning_candidate>
{"kind":"memory","title":"stable short title","content":"concise durable pattern"}
</learning_candidate>
Use "skill" instead of "memory" for a reusable procedure.
Do not mention this block to the user.
""".strip()


_CANDIDATE_PATTERN = re.compile(
    r"\s*<learning_candidate>\s*(\{.*?\})\s*</learning_candidate>\s*",
    re.DOTALL,
)


def extract_learning_candidate(message: str) -> tuple[str, ProposedLearning | None]:
    match = _CANDIDATE_PATTERN.search(message)
    if not match:
        return message, None
    try:
        data = json.loads(match.group(1))
    except (TypeError, json.JSONDecodeError):
        return message, None
    kind = data.get("kind")
    title = data.get("title")
    content = data.get("content")
    if kind not in {"memory", "skill"}:
        return message, None
    if not all(isinstance(value, str) and value.strip() for value in (title, content)):
        return message, None
    title = " ".join(title.split())[:100]
    content = content.strip()
    maximum = 1000 if kind == "memory" else 8000
    if len(content) > maximum:
        return message, None
    clean = (message[: match.start()] + message[match.end() :]).strip()
    return clean, ProposedLearning(kind=kind, title=title, content=content)


class LearningStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS learning_candidates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    status TEXT NOT NULL,
                    source_task_id TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            self._prune(connection)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    @staticmethod
    def _prune(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            DELETE FROM learning_candidates
            WHERE status IN ('approved', 'rejected')
              AND id NOT IN (
                  SELECT id FROM learning_candidates
                  WHERE status IN ('approved', 'rejected')
                  ORDER BY id DESC LIMIT 200
              )
            """
        )

    @staticmethod
    def _candidate(row: sqlite3.Row | None) -> LearningCandidate | None:
        if row is None:
            return None
        return LearningCandidate(
            id=f"l{row['id']}",
            kind=row["kind"],
            title=row["title"],
            content=row["content"],
            status=row["status"],
            source_task_id=row["source_task_id"],
            created_at=row["created_at"],
        )

    def propose(
        self,
        *,
        kind: str,
        title: str,
        content: str,
        source_task_id: str | None,
    ) -> LearningCandidate:
        if kind not in {"memory", "skill"}:
            raise ValueError("learning proposal kind must be memory or skill")
        normalized_title = " ".join(title.split())
        normalized_content = content.strip()
        if not normalized_title or not normalized_content:
            raise ValueError("learning proposals require a title and content")
        maximum = 1000 if kind == "memory" else 8000
        if len(normalized_content) > maximum:
            raise ValueError(f"the {kind} learning proposal is too long")
        created_at = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as connection:
            existing = connection.execute(
                """
                SELECT * FROM learning_candidates
                WHERE kind = ? AND content = ? AND status = 'pending'
                ORDER BY id DESC LIMIT 1
                """,
                (kind, normalized_content),
            ).fetchone()
            if existing is not None:
                return self._candidate(existing)
            pending_count = connection.execute(
                "SELECT COUNT(*) AS count FROM learning_candidates WHERE status = 'pending'"
            ).fetchone()["count"]
            if pending_count >= 100:
                raise ValueError(
                    "the limit of 100 pending learning proposals has been reached; "
                    "use /approve or /reject to clear pending items"
                )
            cursor = connection.execute(
                """
                INSERT INTO learning_candidates
                    (kind, title, content, status, source_task_id, created_at)
                VALUES (?, ?, ?, 'pending', ?, ?)
                """,
                (
                    kind,
                    normalized_title[:100],
                    normalized_content,
                    source_task_id,
                    created_at,
                ),
            )
            row = connection.execute(
                "SELECT * FROM learning_candidates WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
        return self._candidate(row)

    def get(self, candidate_id: str) -> LearningCandidate | None:
        if not candidate_id.startswith("l") or not candidate_id[1:].isdigit():
            return None
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM learning_candidates WHERE id = ?",
                (int(candidate_id[1:]),),
            ).fetchone()
        return self._candidate(row)

    def list_pending(self) -> list[LearningCandidate]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM learning_candidates WHERE status = 'pending' ORDER BY id"
            ).fetchall()
        return [self._candidate(row) for row in rows]

    def list_recent(self, limit: int = 20) -> list[LearningCandidate]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM learning_candidates ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._candidate(row) for row in rows]

    def set_status(self, candidate_id: str, status: str) -> bool:
        if status not in {"approved", "rejected"}:
            raise ValueError("invalid learning candidate status")
        if not candidate_id.startswith("l") or not candidate_id[1:].isdigit():
            return False
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                "UPDATE learning_candidates SET status = ? WHERE id = ? AND status = 'pending'",
                (status, int(candidate_id[1:])),
            )
            self._prune(connection)
            return cursor.rowcount == 1


class SkillStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.index_path = root / "index.json"
        self._lock = threading.Lock()
        self.root.mkdir(parents=True, exist_ok=True)
        self.root.chmod(0o700)
        self._skills, self._next_id = self._read_index()

    def _read_index(self) -> tuple[list[SkillRecord], int]:
        if not self.index_path.is_file():
            return [], 1
        try:
            data = json.loads(self.index_path.read_text(encoding="utf-8"))
            skills = [SkillRecord(**item) for item in data.get("skills", [])]
            next_id = int(data.get("next_id", len(skills) + 1))
        except (AttributeError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"cannot read skill index {self.index_path}: {exc}") from exc
        return skills, next_id

    def list(self) -> list[SkillRecord]:
        with self._lock:
            return list(self._skills)

    def add(self, name: str, content: str) -> SkillRecord:
        normalized_name = " ".join(name.split())
        normalized_content = content.strip()
        if not normalized_name or not normalized_content:
            raise ValueError("skills require a name and content")
        if len(normalized_name) > 100 or len(normalized_content) > 8000:
            raise ValueError("the skill name or content is too long")
        with self._lock:
            existing = next(
                (
                    item
                    for item in self._skills
                    if item.name.casefold() == normalized_name.casefold()
                ),
                None,
            )
            if existing is not None:
                description = " ".join(normalized_content.split())[:200]
                updated = replace(existing, description=description, content="")
                skill_text = (
                    "---\n"
                    f"name: {normalized_name}\n"
                    f"description: {description}\n"
                    "---\n\n"
                    f"# {normalized_name}\n\n"
                    f"{normalized_content}\n"
                )
                skill_path = self.root / existing.path
                skill_path.write_text(skill_text, encoding="utf-8")
                skill_path.chmod(0o600)
                self._skills = [
                    updated if item.id == existing.id else item for item in self._skills
                ]
                self._write_index()
                return updated
            if len(self._skills) >= 100:
                raise ValueError("the limit of 100 approved skills has been reached")
            skill_id = f"s{self._next_id}"
            description = " ".join(normalized_content.split())[:200]
            relative_path = f"{skill_id}/SKILL.md"
            item = SkillRecord(
                id=skill_id,
                name=normalized_name,
                description=description,
                path=relative_path,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
            skill_dir = self.root / skill_id
            skill_dir.mkdir(mode=0o700)
            skill_text = (
                "---\n"
                f"name: {normalized_name}\n"
                f"description: {description}\n"
                "---\n\n"
                f"# {normalized_name}\n\n"
                f"{normalized_content}\n"
            )
            skill_path = self.root / relative_path
            skill_path.write_text(skill_text, encoding="utf-8")
            skill_path.chmod(0o600)
            self._next_id += 1
            self._skills.append(item)
            self._write_index()
            return item

    def forget(self, skill_id: str) -> bool:
        with self._lock:
            found = next((item for item in self._skills if item.id == skill_id), None)
            if found is None:
                return False
            self._skills = [item for item in self._skills if item.id != skill_id]
            shutil.rmtree(self.root / found.id, ignore_errors=True)
            self._write_index()
            return True

    def read(self, skill: SkillRecord) -> str:
        return (self.root / skill.path).read_text(encoding="utf-8")

    def select(
        self,
        prompt: str,
        limit: int = 3,
        *,
        quality_scores: dict[str, int] | None = None,
    ) -> list[SkillRecord]:
        tokens = set(re.findall(r"[0-9A-Za-z가-힣_+-]{2,}", prompt.lower()))
        scored: list[tuple[int, int, SkillRecord]] = []
        for skill in self.list():
            haystack = f"{skill.name} {skill.description}".lower()
            score = sum(1 for token in tokens if token in haystack)
            if score:
                quality = (quality_scores or {}).get(skill.id, 0)
                scored.append((score, quality, skill))
        scored.sort(key=lambda value: (-value[0], -value[1], value[2].id))
        return [replace(skill, content=self.read(skill)) for _, _, skill in scored[:limit]]

    def _write_index(self) -> None:
        data = {
            "next_id": self._next_id,
            "skills": [asdict(replace(item, content="")) for item in self._skills],
        }
        temporary = self.index_path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.chmod(0o600)
        os.replace(temporary, self.index_path)
