from __future__ import annotations

import json
import re
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from .projects import DEFAULT_PROJECT, normalize_project_name
from .secure_io import atomic_write_text, ensure_private_directory, ensure_private_file, read_private_text


ASSET_KINDS = (
    "project",
    "person",
    "commitment",
    "decision",
    "preference",
    "knowledge",
)


@dataclass(frozen=True)
class AssetRecord:
    id: str
    kind: str
    title: str
    content: str
    created_at: str
    updated_at: str
    scope: str = DEFAULT_PROJECT


class VaultStore:
    def __init__(
        self,
        path: Path,
        *,
        max_total_chars: int = 40_000,
        max_records: int = 200,
    ) -> None:
        self.path = path
        self.max_total_chars = max_total_chars
        self.max_records = max_records
        self._lock = threading.Lock()
        ensure_private_directory(path.parent)
        ensure_private_file(path)
        self._records, self._next_id = self._read()

    def _read(self) -> tuple[list[AssetRecord], int]:
        if not self.path.is_file():
            return [], 1
        try:
            data = json.loads(read_private_text(self.path, max_bytes=2_000_000))
            records = [
                AssetRecord(**{**item, "scope": item.get("scope", DEFAULT_PROJECT)})
                for item in data.get("records", [])
            ]
            next_id = int(data.get("next_id", len(records) + 1))
        except (
            AttributeError,
            OSError,
            RuntimeError,
            TypeError,
            UnicodeDecodeError,
            ValueError,
            json.JSONDecodeError,
        ) as exc:
            raise RuntimeError(f"cannot read assistant vault {self.path}: {exc}") from exc
        if next_id < 1 or any(
            record.kind not in ASSET_KINDS
            or not re.fullmatch(r"a[1-9][0-9]*", record.id)
            or not record.title.strip()
            or not record.content.strip()
            or not _valid_scope(record.scope)
            for record in records
        ):
            raise RuntimeError("assistant vault contains an invalid record")
        return records, next_id

    def list(self) -> list[AssetRecord]:
        with self._lock:
            return list(self._records)

    def upsert(
        self,
        kind: str,
        title: str,
        content: str,
        *,
        scope: str = DEFAULT_PROJECT,
    ) -> AssetRecord:
        normalized_kind = kind.strip().lower()
        normalized_title = " ".join(title.split())
        normalized_content = " ".join(content.split())
        normalized_scope = normalize_project_name(scope)
        if normalized_kind not in ASSET_KINDS:
            raise ValueError("asset kind must be one of: " + ", ".join(ASSET_KINDS))
        if not normalized_title or not normalized_content:
            raise ValueError("asset title and content must not be empty")
        if len(normalized_title) > 100 or len(normalized_content) > 2_000:
            raise ValueError("asset title or content is too long")
        with self._lock:
            existing = next(
                (
                    item
                    for item in self._records
                    if item.kind == normalized_kind
                    and item.title.casefold() == normalized_title.casefold()
                    and item.scope == normalized_scope
                ),
                None,
            )
            replaced = len(existing.title) + len(existing.content) if existing else 0
            total = (
                sum(len(item.title) + len(item.content) for item in self._records)
                - replaced
                + len(normalized_title)
                + len(normalized_content)
            )
            if total > self.max_total_chars:
                raise ValueError("assistant vault capacity would be exceeded")
            now = datetime.now(timezone.utc).isoformat()
            if existing is not None:
                item = AssetRecord(
                    id=existing.id,
                    kind=normalized_kind,
                    title=normalized_title,
                    content=normalized_content,
                    created_at=existing.created_at,
                    updated_at=now,
                    scope=normalized_scope,
                )
                self._records = [item if record.id == item.id else record for record in self._records]
            else:
                if len(self._records) >= self.max_records:
                    raise ValueError("assistant vault record limit would be exceeded")
                item = AssetRecord(
                    id=f"a{self._next_id}",
                    kind=normalized_kind,
                    title=normalized_title,
                    content=normalized_content,
                    created_at=now,
                    updated_at=now,
                    scope=normalized_scope,
                )
                self._next_id += 1
                self._records.append(item)
            self._write()
            return item

    def forget(self, asset_id: str) -> bool:
        normalized = asset_id.strip().lower()
        with self._lock:
            remaining = [item for item in self._records if item.id != normalized]
            if len(remaining) == len(self._records):
                return False
            self._records = remaining
            self._write()
            return True

    def select(
        self,
        query: str,
        *,
        scope: str = DEFAULT_PROJECT,
        max_chars: int = 6_000,
    ) -> list[AssetRecord]:
        tokens = set(re.findall(r"[0-9A-Za-z가-힣_+-]{2,}", query.casefold()))
        normalized_scope = normalize_project_name(scope)
        with self._lock:
            ranked = sorted(
                [item for item in self._records if item.scope == normalized_scope],
                key=lambda item: (
                    sum(
                        3 * (token in item.title.casefold())
                        + (token in item.content.casefold())
                        for token in tokens
                    ),
                    item.updated_at,
                ),
                reverse=True,
            )
            chosen: list[AssetRecord] = []
            used = 0
            for item in ranked:
                relevant = not tokens or any(
                    token in f"{item.title} {item.content}".casefold() for token in tokens
                )
                if not relevant:
                    continue
                size = len(item.kind) + len(item.title) + len(item.content) + 20
                if chosen and used + size > max_chars:
                    break
                chosen.append(item)
                used += size
            return chosen

    def _write(self) -> None:
        atomic_write_text(
            self.path,
            json.dumps(
                {
                    "next_id": self._next_id,
                    "records": [asdict(item) for item in self._records],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
        )


def _valid_scope(value: str) -> bool:
    try:
        return normalize_project_name(value) == value
    except (TypeError, ValueError):
        return False
