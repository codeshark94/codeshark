import tempfile
import unittest
from pathlib import Path

from codex_codeshark.recall import RecallStore


class RecallStoreTests(unittest.TestCase):
    def test_search_tracks_provenance_usage_and_feedback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = RecallStore(Path(directory) / "agent.db")
            store.upsert(
                kind="memory",
                source_id="m1",
                title="Testing preference",
                content="Prefer Python unittest",
                source_task_id="t1",
            )
            match = store.search("unittest")[0]
            self.assertEqual((match.source_id, match.source_task_id), ("m1", "t1"))
            store.mark_used("memory", ("m1",))
            store.record_feedback(memory_ids=("m1",), skill_ids=(), rating="good")
            stats = store.stats("memory", "m1")
            self.assertEqual((stats.use_count, stats.good_count, stats.bad_count), (1, 1, 0))

    def test_upsert_preserves_quality_counters_and_delete_removes_entry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = RecallStore(Path(directory) / "agent.db")
            values = dict(
                kind="skill",
                source_id="s1",
                title="Testing",
                content="Run tests",
                source_task_id=None,
            )
            store.upsert(**values)
            store.mark_used("skill", ("s1",))
            store.upsert(**{**values, "content": "Run all tests"})
            self.assertEqual(store.stats("skill", "s1").use_count, 1)
            self.assertTrue(store.delete("skill", "s1"))
            self.assertIsNone(store.stats("skill", "s1"))


if __name__ == "__main__":
    unittest.main()
