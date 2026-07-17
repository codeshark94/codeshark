import json
import tempfile
import unittest
from pathlib import Path

from codex_codeshark.state import StateStore


class StateStoreTests(unittest.TestCase):
    def test_persists_offset_and_chat_scoped_sessions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            store = StateStore(path)
            store.set_last_update_id(42)
            store.set_session_thread_id(123, "private-thread")
            store.record_session_turn(123, "private-thread")
            store.record_session_turn(123, "private-thread")
            store.record_session_turn(-100123, "group-thread")
            restored = StateStore(path).snapshot()
            self.assertEqual(restored.last_update_id, 42)
            self.assertEqual(
                restored.chat_sessions["123"].codex_thread_id,
                "private-thread",
            )
            self.assertEqual(restored.chat_sessions["123"].session_turn_count, 2)
            self.assertEqual(
                restored.chat_sessions["-100123"].codex_thread_id,
                "group-thread",
            )

            store.set_session_thread_id(123, None)
            self.assertIsNone(store.session_snapshot(123).codex_thread_id)
            self.assertEqual(store.session_snapshot(-100123).codex_thread_id, "group-thread")

    def test_migrates_legacy_session_to_administrator_private_chat(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            path.write_text(
                json.dumps(
                    {
                        "last_update_id": 42,
                        "codex_thread_id": "legacy-thread",
                        "session_turn_count": 7,
                    }
                ),
                encoding="utf-8",
            )
            store = StateStore(path)

            self.assertTrue(store.migrate_legacy_session(123))
            self.assertEqual(store.session_snapshot(123).codex_thread_id, "legacy-thread")
            self.assertEqual(store.session_snapshot(123).session_turn_count, 7)
            self.assertFalse(store.migrate_legacy_session(123))
            self.assertEqual(StateStore(path).snapshot().last_update_id, 42)


if __name__ == "__main__":
    unittest.main()
