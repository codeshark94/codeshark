import tempfile
import unittest
from pathlib import Path

from codex_codeshark.learning import (
    LearningStore,
    SkillStore,
    extract_learning_candidate,
)


class LearningStoreTests(unittest.TestCase):
    def test_persists_pending_candidate_and_status(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "agent.db"
            store = LearningStore(path)
            candidate = store.propose(
                kind="memory",
                title="테스트 선호",
                content="사용자는 unittest를 선호한다",
                source_task_id="t1",
            )
            self.assertEqual(candidate.id, "l1")
            self.assertEqual([item.id for item in LearningStore(path).list_pending()], ["l1"])
            self.assertTrue(store.set_status("l1", "approved"))
            self.assertEqual(store.list_pending(), [])

    def test_extracts_and_hides_model_candidate(self) -> None:
        message = """작업을 완료했습니다.
<learning_candidate>
{"kind":"skill","title":"테스트 실행","content":"unittest를 실행하고 결과를 확인한다"}
</learning_candidate>"""
        clean, proposed = extract_learning_candidate(message)
        self.assertEqual(clean, "작업을 완료했습니다.")
        self.assertEqual(proposed.kind, "skill")
        self.assertEqual(proposed.title, "테스트 실행")

    def test_ignores_invalid_candidate_marker(self) -> None:
        message = "done <learning_candidate>not-json</learning_candidate>"
        clean, proposed = extract_learning_candidate(message)
        self.assertEqual(clean, message)
        self.assertIsNone(proposed)


class SkillStoreTests(unittest.TestCase):
    def test_persists_and_selects_only_relevant_skill(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "skills"
            store = SkillStore(root)
            testing = store.add("Python 테스트", "unittest 테스트 실행 절차")
            store.add("배포", "운영 서버 배포 절차")

            restored = SkillStore(root)
            selected = restored.select("Python unittest 테스트를 실행해줘")
            self.assertEqual([item.id for item in selected], [testing.id])
            self.assertIn("unittest", restored.read(testing))

    def test_forgets_skill_and_removes_its_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SkillStore(Path(directory) / "skills")
            skill = store.add("테스트", "테스트 절차")
            path = store.root / skill.path
            self.assertTrue(path.is_file())
            self.assertTrue(store.forget(skill.id))
            self.assertFalse(path.exists())

    def test_approved_skill_can_be_improved_in_place(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SkillStore(Path(directory) / "skills")
            original = store.add("테스트", "기존 절차")
            updated = store.add("테스트", "개선된 절차")
            self.assertEqual(updated.id, original.id)
            self.assertIn("개선된 절차", store.read(updated))


if __name__ == "__main__":
    unittest.main()
