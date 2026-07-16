import tempfile
import unittest
from pathlib import Path

from codex_codeshark.state import StateStore


class StateStoreTests(unittest.TestCase):
    def test_persists_offset_and_current_thread(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            store = StateStore(path)
            store.set_last_update_id(42)
            store.set_codex_thread_id("thread-1")
            store.record_codex_turn("thread-1")
            store.record_codex_turn("thread-1")
            restored = StateStore(path).snapshot()
            self.assertEqual(restored.last_update_id, 42)
            self.assertEqual(restored.codex_thread_id, "thread-1")
            self.assertEqual(restored.session_turn_count, 2)

            store.set_codex_thread_id(None)
            self.assertEqual(store.snapshot().session_turn_count, 0)


if __name__ == "__main__":
    unittest.main()
