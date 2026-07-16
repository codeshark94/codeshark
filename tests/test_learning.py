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
                title="Testing preference",
                content="The user prefers unittest",
                source_task_id="t1",
            )
            self.assertEqual(candidate.id, "l1")
            self.assertEqual([item.id for item in LearningStore(path).list_pending()], ["l1"])
            self.assertTrue(store.set_status("l1", "approved"))
            self.assertEqual(store.list_pending(), [])

    def test_extracts_and_hides_model_candidate(self) -> None:
        message = """Task completed.
<learning_candidate>
{"kind":"skill","title":"Run tests","content":"Run unittest and inspect the result"}
</learning_candidate>"""
        clean, proposed = extract_learning_candidate(message)
        self.assertEqual(clean, "Task completed.")
        self.assertEqual(proposed.kind, "skill")
        self.assertEqual(proposed.title, "Run tests")

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
            testing = store.add("Python testing", "unittest execution procedure")
            store.add("Deployment", "production deployment procedure")

            restored = SkillStore(root)
            selected = restored.select("Run the Python unittest tests")
            self.assertEqual([item.id for item in selected], [testing.id])
            self.assertIn("unittest", restored.read(testing))

    def test_forgets_skill_and_removes_its_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SkillStore(Path(directory) / "skills")
            skill = store.add("Testing", "Test procedure")
            path = store.root / skill.path
            self.assertTrue(path.is_file())
            self.assertTrue(store.forget(skill.id))
            self.assertFalse(path.exists())

    def test_approved_skill_can_be_improved_in_place(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SkillStore(Path(directory) / "skills")
            original = store.add("Testing", "Original procedure")
            updated = store.add("Testing", "Improved procedure")
            self.assertEqual(updated.id, original.id)
            self.assertIn("Improved procedure", store.read(updated))


if __name__ == "__main__":
    unittest.main()
