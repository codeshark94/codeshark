import tempfile
import unittest
from pathlib import Path

from codex_codeshark.automation import AgentStore
from codex_codeshark.config import Config
from codex_codeshark.local_console import (
    LOCAL_CONSOLE_CHAT_ID,
    LOCAL_CONSOLE_SOURCE,
    local_history,
    submit_local_request,
)


class LocalConsoleTests(unittest.TestCase):
    def test_submits_a_direct_local_task_and_stages_attachments(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            workspace.mkdir()
            binary = root / "codex"
            binary.write_text("", encoding="utf-8")
            source = root / "brief.txt"
            source.write_text("local attachment", encoding="utf-8")
            config = Config(
                allowed_user_ids=frozenset({123}),
                workdir=workspace,
                codex_binary=binary,
                state_path=root / "runtime" / "state.json",
            )

            submission = submit_local_request(
                config,
                "Summarize this file.",
                attachments=(source,),
            )

            task = AgentStore(root / "runtime" / "agent.db").get_task(submission.task_id)
            self.assertEqual(task.chat_id, LOCAL_CONSOLE_CHAT_ID)
            self.assertEqual(task.source, LOCAL_CONSOLE_SOURCE)
            self.assertTrue(task.approved)
            self.assertIn("Summarize this file.", task.prompt)
            self.assertTrue(submission.attachments[0].is_file())
            self.assertEqual(submission.attachments[0].read_text(encoding="utf-8"), "local attachment")
            messages = local_history(config)
            self.assertEqual(messages[-1].role, "user")
            self.assertEqual(messages[-1].attachments, (str(submission.attachments[0]),))

    def test_local_history_isolated_from_telegram_task_records(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            workspace.mkdir()
            binary = root / "codex"
            binary.write_text("", encoding="utf-8")
            config = Config(
                allowed_user_ids=frozenset({123}),
                workdir=workspace,
                codex_binary=binary,
                state_path=root / "runtime" / "state.json",
            )
            store = AgentStore(root / "runtime" / "agent.db")
            store.enqueue_task(123, "telegram task", source="telegram", ephemeral=False)
            store.append_local_message("assistant", "local result", task_id="local-task")

            messages = local_history(config)

            self.assertEqual([(message.role, message.text) for message in messages], [("assistant", "local result")])


if __name__ == "__main__":
    unittest.main()
