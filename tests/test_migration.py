import json
import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path

from codex_codeshark.automation import AgentStore
from codex_codeshark.learning import LearningStore, SkillStore
from codex_codeshark.memory import FeedbackStore, MemoryStore
from codex_codeshark.migration import (
    MigrationError,
    export_personal_data,
    import_personal_data,
)
from codex_codeshark.recall import RecallStore


class PersonalDataMigrationTests(unittest.TestCase):
    def _build_personal_data(self, runtime: Path) -> tuple[str, str]:
        memory = MemoryStore(runtime / "memory.json").add("Answer in English")
        skill = SkillStore(runtime / "skills").add("Testing", "Verify with unittest")
        FeedbackStore(runtime / "feedback.jsonl").record(
            task_id="t-complete",
            rating="good",
            note="accurate",
            thread_id="thread-old",
            memory_ids=(memory.id,),
            skill_ids=(skill.id,),
        )
        database = runtime / "agent.db"
        learning = LearningStore(database)
        learning.propose(
            kind="memory",
            title="Response preference",
            content="Reply concisely",
            source_task_id=None,
        )
        store = AgentStore(database)
        store.record_delivery_failure(123, "private final result", "offline")
        store.enable_group(-100123, "Private group", 123)
        store.append_group_context(-100123, 456, "private question", "private answer")
        store.remember_group_addressed_message(-100123, 77)
        store.enqueue_task(
            -100123,
            "guest question",
            source="telegram-group",
            ephemeral=True,
            restricted=True,
        )
        RecallStore(database).upsert(
            kind="memory",
            source_id=memory.id,
            title="Response language",
            content=memory.text,
            source_task_id="t-complete",
        )
        task = store.enqueue_task(
            123,
            "check server",
            source="telegram",
            ephemeral=False,
        )
        schedule = store.create_schedule(
            123,
            kind="heartbeat",
            expression="600",
            prompt="check server status",
            next_run_at=100.0,
        )
        (runtime / "state.json").write_text(
            '{"codex_thread_id":"must-not-migrate"}',
            encoding="utf-8",
        )
        return task.id, schedule.id

    def test_exports_and_imports_only_portable_personal_data(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            target = root / "target"
            archive = root / "personal.codeshark.zip"
            task_id, schedule_id = self._build_personal_data(source)

            exported = export_personal_data(archive, runtime_dir=source)
            self.assertIn("runtime/memory.json", exported.files)
            with zipfile.ZipFile(archive) as bundle:
                names = set(bundle.namelist())
                manifest = json.loads(bundle.read("manifest.json"))
            self.assertNotIn("runtime/state.json", names)
            self.assertNotIn("config.local.toml", names)
            self.assertIn("Telegram bot token", manifest["excluded"])

            imported = import_personal_data(archive, runtime_dir=target)
            self.assertEqual(imported.files, exported.files)
            self.assertEqual(
                MemoryStore(target / "memory.json").list()[0].text,
                "Answer in English",
            )
            self.assertEqual(SkillStore(target / "skills").list()[0].name, "Testing")
            self.assertEqual(
                LearningStore(target / "agent.db").list_pending()[0].title,
                "Response preference",
            )

            store = AgentStore(target / "agent.db")
            task = store.get_task(task_id)
            self.assertEqual(task.status, "cancelled")
            self.assertEqual(task.prompt, "")
            self.assertEqual(store.get_schedule(schedule_id).status, "paused")
            self.assertEqual(store.list_failed_deliveries(), [])
            self.assertEqual(store.list_groups(), [])
            self.assertEqual(store.group_context(-100123, 456), [])
            self.assertFalse(store.is_group_addressed_message(-100123, 77))
            self.assertFalse(any(item.restricted for item in store.list_tasks()))
            recalled = RecallStore(target / "agent.db").search("English")[0]
            self.assertEqual(recalled.source_task_id, "t-complete")

    def test_import_requires_force_before_replacing_personal_data(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            target = root / "target"
            archive = root / "personal.codeshark.zip"
            self._build_personal_data(source)
            export_personal_data(archive, runtime_dir=source)
            MemoryStore(target / "memory.json").add("existing data")

            with self.assertRaisesRegex(MigrationError, "--force"):
                import_personal_data(archive, runtime_dir=target)
            import_personal_data(archive, runtime_dir=target, replace=True)
            self.assertEqual(
                MemoryStore(target / "memory.json").list()[0].text,
                "Answer in English",
            )

    def test_rejects_unlisted_archive_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "bad.codeshark.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr(
                    "manifest.json",
                    json.dumps(
                        {
                            "format": "codex-codeshark-personal-data",
                            "version": 1,
                            "files": {
                                "../../secret": {
                                    "size": 1,
                                    "sha256": "0" * 64,
                                }
                            },
                        }
                    ),
                )
                bundle.writestr("../../secret", "x")
            with self.assertRaisesRegex(MigrationError, "invalid path"):
                import_personal_data(archive, runtime_dir=Path(directory) / "target")

    def test_rejects_malicious_imported_skill_index_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "bad-skill.codeshark.zip"
            external = root / "external.md"
            external.write_text("sentinel", encoding="utf-8")
            index = json.dumps(
                {
                    "next_id": 2,
                    "skills": [
                        {
                            "id": "s1",
                            "name": "Injected",
                            "description": "Injected",
                            "path": str(external),
                            "created_at": "2026-01-01T00:00:00+00:00",
                            "content": "",
                        }
                    ],
                }
            ).encode("utf-8")
            name = "runtime/skills/index.json"
            manifest = {
                "format": "codex-codeshark-personal-data",
                "version": 1,
                "files": {
                    name: {
                        "size": len(index),
                        "sha256": hashlib.sha256(index).hexdigest(),
                    }
                },
            }
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("manifest.json", json.dumps(manifest))
                bundle.writestr(name, index)

            with self.assertRaisesRegex(MigrationError, "invalid imported skill index"):
                import_personal_data(archive, runtime_dir=root / "target")
            self.assertEqual(external.read_text(encoding="utf-8"), "sentinel")


if __name__ == "__main__":
    unittest.main()
