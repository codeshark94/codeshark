import json
import os
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from codex_codeshark.codex_runner import CodexRunner, parse_codex_events


class CodexRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = CodexRunner(
            binary=Path("/tmp/codex"),
            profile="codex-codeshark",
            workdir=Path("/tmp/workspace"),
            timeout_seconds=60,
            mcp_known_servers=("github", "docs"),
            mcp_allowed_tools=(("github", ("list_issues",)),),
        )

    def test_builds_new_session_command(self) -> None:
        command = self.runner.build_command("hello", None)
        self.assertEqual(command[-3:], ["--json", "--skip-git-repo-check", "hello"])
        self.assertIn("codex-codeshark", command)

    def test_builds_resume_command(self) -> None:
        command = self.runner.build_command("continue", "thread-123")
        self.assertEqual(
            command[-5:],
            ["resume", "--json", "--skip-git-repo-check", "thread-123", "continue"],
        )

    def test_builds_ephemeral_command_with_mcp_allowlist(self) -> None:
        command = self.runner.build_command("scheduled", None, ephemeral=True)
        self.assertIn("--ephemeral", command)
        self.assertIn("mcp_servers.github.enabled=true", command)
        self.assertIn('mcp_servers.github.enabled_tools=["list_issues"]', command)
        self.assertIn("mcp_servers.docs.enabled=false", command)

    def test_builds_force_delete_session_command(self) -> None:
        command = self.runner.build_delete_command("thread-123")
        self.assertEqual(command[-3:], ["delete", "--force", "thread-123"])
        self.assertIn("codex-codeshark", command)

    @patch("codex_codeshark.codex_runner.subprocess.run")
    def test_deletes_session_without_passing_telegram_token(self, run) -> None:
        run.return_value = subprocess.CompletedProcess([], 0, "", "")
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "secret"}):
            self.runner.delete_session("thread-123")
        kwargs = run.call_args.kwargs
        self.assertNotIn("TELEGRAM_BOT_TOKEN", kwargs["env"])
        self.assertEqual(kwargs["timeout"], 30)

    @patch("codex_codeshark.codex_runner.subprocess.run")
    def test_keeps_delete_failure_visible(self, run) -> None:
        run.return_value = subprocess.CompletedProcess([], 1, "", "delete failed")
        with self.assertRaisesRegex(RuntimeError, "delete failed"):
            self.runner.delete_session("thread-123")

    def test_parses_thread_and_agent_message(self) -> None:
        output = "\n".join(
            [
                json.dumps({"type": "thread.started", "thread_id": "abc"}),
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {"type": "agent_message", "text": "working"},
                    }
                ),
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {"type": "agent_message", "text": "done"},
                    }
                ),
            ]
        )
        self.assertEqual(parse_codex_events(output), ("done", "abc"))


if __name__ == "__main__":
    unittest.main()
