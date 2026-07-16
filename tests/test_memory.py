import json
import tempfile
import unittest
from pathlib import Path

from codex_codeshark.learning import SkillStore
from codex_codeshark.memory import FeedbackStore, MemoryStore, compose_prompt


class MemoryStoreTests(unittest.TestCase):
    def test_persists_lists_and_forgets_memories(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "memory.json"
            store = MemoryStore(path)
            first = store.add("Python 테스트는 unittest를 사용한다")
            second = store.add("답변은 한국어로 한다")

            restored = MemoryStore(path)
            self.assertEqual([item.text for item in restored.list()], [first.text, second.text])
            self.assertTrue(restored.forget(first.id))
            self.assertFalse(restored.forget("missing"))
            self.assertEqual([item.id for item in MemoryStore(path).list()], [second.id])

    def test_rejects_duplicate_memory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = MemoryStore(Path(directory) / "memory.json")
            store.add("같은 기억")
            with self.assertRaises(ValueError):
                store.add("같은 기억")

    def test_enforces_total_memory_capacity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = MemoryStore(Path(directory) / "memory.json", max_total_chars=20)
            store.add("a" * 15)
            with self.assertRaises(ValueError):
                store.add("b" * 6)

    def test_compose_prompt_includes_approved_memory_and_current_request(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = MemoryStore(Path(directory) / "memory.json")
            item = store.add("답변은 한국어로 한다")
            prompt, memory_ids, skill_ids = compose_prompt("현재 요청", store.list())
            self.assertIn("승인한 장기 메모리", prompt)
            self.assertIn(item.text, prompt)
            self.assertTrue(prompt.endswith("현재 요청"))
            self.assertEqual(memory_ids, (item.id,))
            self.assertEqual(skill_ids, ())

    def test_compose_prompt_limits_memory_size(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = MemoryStore(Path(directory) / "memory.json")
            store.add("a" * 20)
            second = store.add("b" * 20)
            prompt, memory_ids, skill_ids = compose_prompt(
                "요청",
                store.list(),
                max_memory_chars=30,
            )
            self.assertIn(second.text, prompt)
            self.assertNotIn("a" * 20, prompt)
            self.assertEqual(memory_ids, (second.id,))
            self.assertEqual(skill_ids, ())

    def test_compose_prompt_includes_only_selected_skill(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            skills = SkillStore(Path(directory) / "skills")
            selected = skills.add("Python 테스트", "unittest 실행 절차")
            skills.add("배포", "운영 서버 배포 절차")
            prompt, _, skill_ids = compose_prompt(
                "unittest 테스트를 실행해줘",
                [],
                skills.select("unittest 테스트를 실행해줘"),
            )
            self.assertIn("unittest 실행 절차", prompt)
            self.assertNotIn("운영 서버 배포 절차", prompt)
            self.assertEqual(skill_ids, (selected.id,))


class FeedbackStoreTests(unittest.TestCase):
    def test_appends_feedback_without_prompt_or_response(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "feedback.jsonl"
            store = FeedbackStore(path)
            store.record(
                task_id="task-1",
                rating="good",
                note="정확함",
                thread_id="thread-1",
                memory_ids=("m1",),
                skill_ids=("s1",),
            )
            event = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(event["rating"], "good")
            self.assertEqual(event["memory_ids"], ["m1"])
            self.assertEqual(event["skill_ids"], ["s1"])
            self.assertNotIn("prompt", event)
            self.assertNotIn("response", event)

    def test_rejects_unknown_rating(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = FeedbackStore(Path(directory) / "feedback.jsonl")
            with self.assertRaises(ValueError):
                store.record(
                    task_id="task-1",
                    rating="maybe",
                    note="",
                    thread_id=None,
                    memory_ids=(),
                    skill_ids=(),
                )


if __name__ == "__main__":
    unittest.main()
