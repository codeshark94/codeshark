import json
import tempfile
import unittest
from pathlib import Path

from codex_codeshark.state import StateStore


class StateStoreTests(unittest.TestCase):
    def test_persists_owner_onboarding_request(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            store = StateStore(path)
            self.assertFalse(store.owner_onboarding_requested())
            store.mark_owner_onboarding_requested()
            self.assertTrue(StateStore(path).owner_onboarding_requested())
            store.clear_owner_onboarding_requested()
            self.assertFalse(StateStore(path).owner_onboarding_requested())

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

    def test_keeps_temporary_sessions_separate_by_project(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = StateStore(Path(directory) / "state.json")
            store.set_session_thread_id(123, "general-thread", "General")
            store.record_session_turn(123, "general-thread", "General")
            store.set_active_project(123, "Research")
            store.set_session_thread_id(123, "research-thread", "Research")
            store.record_session_turn(123, "research-thread", "Research")

            restored = StateStore(Path(directory) / "state.json")
            self.assertEqual(restored.active_project(123), "Research")
            self.assertEqual(
                restored.session_snapshot(123, "General").codex_thread_id,
                "general-thread",
            )
            self.assertEqual(
                restored.session_snapshot(123, "Research").codex_thread_id,
                "research-thread",
            )
            restored.set_session_thread_id(123, None, "Research")
            self.assertEqual(
                restored.session_snapshot(123, "General").session_turn_count,
                1,
            )

    def test_expires_only_the_idle_source_and_project_context(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = StateStore(Path(directory) / "state.json")
            retention = 14 * 24 * 60 * 60
            now = 2_000_000.0
            store.set_session_thread_id(0, "local-research", "Research", now=now - retention)
            store.set_session_thread_id(123, "telegram-research", "Research", now=now - 1)
            store.set_session_thread_id(0, "local-general", "General", now=now - 1)

            self.assertTrue(
                store.session_idle_expired(0, "Research", retention_seconds=retention, now=now)
            )
            self.assertFalse(
                store.session_idle_expired(123, "Research", retention_seconds=retention, now=now)
            )
            self.assertFalse(
                store.session_idle_expired(0, "General", retention_seconds=retention, now=now)
            )

    def test_persists_automatic_file_delivery_per_chat(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            store = StateStore(path)

            self.assertFalse(store.automatic_file_delivery_enabled(123))
            store.set_automatic_file_delivery(123, True)

            restored = StateStore(path)
            self.assertTrue(restored.automatic_file_delivery_enabled(123))
            self.assertFalse(restored.automatic_file_delivery_enabled(456))

    def test_preserves_an_interrupted_project_session_until_a_successful_turn(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            store = StateStore(path)
            store.set_session_thread_id(123, "thread-1", "Research")
            store.mark_session_interrupted(123, "Research")

            restored = StateStore(path)
            self.assertTrue(restored.session_interrupted(123, "Research"))
            restored.record_session_turn(123, "thread-1", "Research")
            self.assertFalse(restored.session_interrupted(123, "Research"))


if __name__ == "__main__":
    unittest.main()
