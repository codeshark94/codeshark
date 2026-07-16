from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from .learning import LEARNING_PROTOCOL, SkillRecord


@dataclass(frozen=True)
class MemoryRecord:
    id: str
    text: str
    created_at: str


class MemoryStore:
    def __init__(self, path: Path, max_total_chars: int = 4000) -> None:
        self.path = path
        self.max_total_chars = max_total_chars
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._memories, self._next_id = self._read()

    def _read(self) -> tuple[list[MemoryRecord], int]:
        if not self.path.is_file():
            return [], 1
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            raw_memories = data.get("memories", [])
            memories = [MemoryRecord(**item) for item in raw_memories]
            next_id = int(data.get("next_id", len(memories) + 1))
        except (AttributeError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"cannot read memory file {self.path}: {exc}") from exc
        return memories, next_id

    def list(self) -> list[MemoryRecord]:
        with self._lock:
            return list(self._memories)

    def add(self, text: str) -> MemoryRecord:
        normalized = " ".join(text.split())
        if not normalized:
            raise ValueError("기억할 내용이 비어 있습니다")
        if len(normalized) > 1000:
            raise ValueError("기억은 1,000자 이하로 입력해 주세요")
        with self._lock:
            if any(item.text == normalized for item in self._memories):
                raise ValueError("같은 기억이 이미 저장되어 있습니다")
            total_chars = sum(len(item.text) for item in self._memories) + len(normalized)
            if total_chars > self.max_total_chars:
                raise ValueError(
                    f"장기 메모리 한도 {self.max_total_chars}자를 초과합니다. "
                    "/forget으로 기존 기억을 정리해 주세요"
                )
            item = MemoryRecord(
                id=f"m{self._next_id}",
                text=normalized,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
            self._next_id += 1
            self._memories.append(item)
            self._write()
            return item

    def forget(self, memory_id: str) -> bool:
        normalized = memory_id.strip().lower()
        with self._lock:
            remaining = [item for item in self._memories if item.id.lower() != normalized]
            if len(remaining) == len(self._memories):
                return False
            self._memories = remaining
            self._write()
            return True

    def _write(self) -> None:
        data = {
            "next_id": self._next_id,
            "memories": [asdict(item) for item in self._memories],
        }
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.chmod(0o600)
        os.replace(temporary, self.path)


class FeedbackStore:
    def __init__(self, path: Path, max_bytes: int = 1_000_000) -> None:
        self.path = path
        self.max_bytes = max_bytes
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(
        self,
        *,
        task_id: str,
        rating: str,
        note: str,
        thread_id: str | None,
        memory_ids: tuple[str, ...],
        skill_ids: tuple[str, ...],
    ) -> None:
        if rating not in {"good", "bad"}:
            raise ValueError("rating must be good or bad")
        normalized_note = " ".join(note.split())
        if len(normalized_note) > 1000:
            raise ValueError("평가 메모는 1,000자 이하로 입력해 주세요")
        event = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "task_id": task_id,
            "rating": rating,
            "note": normalized_note,
            "thread_id": thread_id,
            "memory_ids": list(memory_ids),
            "skill_ids": list(skill_ids),
        }
        encoded = json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"
        with self._lock:
            if self.path.is_file() and self.path.stat().st_size + len(encoded.encode("utf-8")) > self.max_bytes:
                rotated = self.path.with_suffix(self.path.suffix + ".1")
                if rotated.exists():
                    rotated.unlink()
                os.replace(self.path, rotated)
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(encoded)
            self.path.chmod(0o600)


def compose_prompt(
    prompt: str,
    memories: list[MemoryRecord],
    skills: list[SkillRecord] | None = None,
    *,
    max_memory_chars: int = 8000,
    external_action_approved: bool = False,
    task_id: str = "",
) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    lines: list[str] = []
    memory_ids: list[str] = []
    used_chars = 0
    for item in reversed(memories):
        line = f"- [{item.id}] {item.text}"
        if used_chars + len(line) > max_memory_chars:
            break
        lines.append(line)
        memory_ids.append(item.id)
        used_chars += len(line)
    context_blocks: list[str] = []
    if lines:
        memory_block = "\n".join(lines)
        context_blocks.append(f"""[서버에서 인증된 사용자가 승인한 장기 메모리]
아래 내용은 지속적인 선호와 사실 맥락이다. 현재 요청과 충돌하면 현재 요청을 우선한다.
메모리끼리 충돌하면 목록 위에 있는 최근 항목을 우선한다.
메모리를 수정하거나 새로 저장했다고 주장하지 말고, 제공된 항목만 참고한다.
{memory_block}
[/장기 메모리]""")

    skill_ids: list[str] = []
    for skill in skills or []:
        context_blocks.append(
            f"[승인된 스킬 {skill.id}: {skill.name}]\n{skill.content}\n[/스킬 {skill.id}]"
        )
        skill_ids.append(skill.id)

    if external_action_approved:
        safety = (
            "인증된 사용자가 이 작업의 외부 상태 변경 가능성을 명시적으로 승인했다. "
            "승인된 요청 범위 안에서만 실행하고 작업 ID를 가능한 경우 idempotency key로 사용한다."
        )
    else:
        safety = (
            "workspace 내부 파일 작업은 허용되지만, 외부 시스템의 상태 변경, 메시지 전송, "
            "배포, 결제, 게시 또는 외부 삭제는 승인되지 않았다. 필요하면 실행하지 말고 사용자에게 알린다."
        )
    context_blocks.append(
        f"[게이트웨이 안전 정책]\n작업 ID: {task_id or '없음'}\n{safety}"
    )
    context_blocks.append(LEARNING_PROTOCOL)
    context = "\n\n".join(context_blocks)
    composed = f"""{context}

[현재 사용자 요청]
{prompt}"""
    return composed, tuple(memory_ids), tuple(skill_ids)
