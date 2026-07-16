import json
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


class PersonalDataMigrationTests(unittest.TestCase):
    def _build_personal_data(self, runtime: Path) -> tuple[str, str]:
        memory = MemoryStore(runtime / "memory.json").add("답변은 한국어로 한다")
        skill = SkillStore(runtime / "skills").add("테스트", "unittest로 검증한다")
        FeedbackStore(runtime / "feedback.jsonl").record(
            task_id="t-complete",
            rating="good",
            note="정확함",
            thread_id="thread-old",
            memory_ids=(memory.id,),
            skill_ids=(skill.id,),
        )
        database = runtime / "agent.db"
        learning = LearningStore(database)
        learning.propose(
            kind="memory",
            title="응답 선호",
            content="짧게 답한다",
            source_task_id=None,
        )
        store = AgentStore(database)
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
            prompt="서버 상태 확인",
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
                "답변은 한국어로 한다",
            )
            self.assertEqual(SkillStore(target / "skills").list()[0].name, "테스트")
            self.assertEqual(LearningStore(target / "agent.db").list_pending()[0].title, "응답 선호")

            store = AgentStore(target / "agent.db")
            task = store.get_task(task_id)
            self.assertEqual(task.status, "cancelled")
            self.assertEqual(task.prompt, "")
            self.assertEqual(store.get_schedule(schedule_id).status, "paused")

    def test_import_requires_force_before_replacing_personal_data(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            target = root / "target"
            archive = root / "personal.codeshark.zip"
            self._build_personal_data(source)
            export_personal_data(archive, runtime_dir=source)
            MemoryStore(target / "memory.json").add("기존 데이터")

            with self.assertRaisesRegex(MigrationError, "--force"):
                import_personal_data(archive, runtime_dir=target)
            import_personal_data(archive, runtime_dir=target, replace=True)
            self.assertEqual(
                MemoryStore(target / "memory.json").list()[0].text,
                "답변은 한국어로 한다",
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


if __name__ == "__main__":
    unittest.main()
