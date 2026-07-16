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
            restricted_workdir=Path("/tmp/group-workspace"),
            restricted_codex_home=Path("/tmp/group-codex-home"),
            timeout_seconds=60,
            mcp_known_servers=("github", "docs"),
            mcp_allowed_tools=(("github", ("list_issues",)),),
        )

    def test_builds_new_session_command(self) -> None:
        command = self.runner.build_command("hello", None)
        self.assertEqual(command[-3:], ["--json", "--skip-git-repo-check", "hello"])
        self.assertIn("codex-codeshark", command)
        self.assertIn("sandbox_workspace_write.network_access=false", command)

    def test_pins_configured_model_for_admin_tasks(self) -> None:
        runner = CodexRunner(
            binary=Path("/tmp/codex"),
            profile="codex-codeshark",
            workdir=Path("/tmp/workspace"),
            timeout_seconds=60,
            model="gpt-5.5",
            model_reasoning_effort="xhigh",
        )
        command = runner.build_command("hello", None)
        self.assertIn("--model", command)
        self.assertIn("gpt-5.5", command)
        self.assertIn('model_reasoning_effort="xhigh"', command)

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

    def test_child_environment_uses_strict_allowlist(self) -> None:
        with patch.dict(
            os.environ,
            {
                "TELEGRAM_BOT_TOKEN": "telegram-secret",
                "OPENAI_API_KEY": "openai-secret",
                "AWS_SECRET_ACCESS_KEY": "aws-secret",
                "SSH_AUTH_SOCK": "/tmp/ssh.sock",
                "LANG": "en_US.UTF-8",
            },
            clear=True,
        ):
            environment = self.runner._child_env()
        self.assertEqual(environment["LANG"], "en_US.UTF-8")
        self.assertEqual(environment["NO_COLOR"], "1")
        self.assertNotIn("TELEGRAM_BOT_TOKEN", environment)
        self.assertNotIn("OPENAI_API_KEY", environment)
        self.assertNotIn("AWS_SECRET_ACCESS_KEY", environment)
        self.assertNotIn("SSH_AUTH_SOCK", environment)

    def test_network_access_can_be_explicitly_enabled(self) -> None:
        runner = CodexRunner(
            binary=Path("/tmp/codex"),
            profile="codex-codeshark",
            workdir=Path("/tmp/workspace"),
            timeout_seconds=60,
            network_access=True,
        )
        self.assertIn(
            "sandbox_workspace_write.network_access=true",
            runner.build_command("hello", None),
        )

    def test_delegated_project_roots_are_added_to_admin_sandbox(self) -> None:
        runner = CodexRunner(
            binary=Path("/tmp/codex"),
            profile="codex-codeshark",
            workdir=Path("/tmp/workspace"),
            timeout_seconds=60,
            additional_write_roots=(Path("/tmp/project-a"), Path("/tmp/project-b")),
        )
        command = runner.build_command("work across projects", None)
        self.assertEqual(command.count("--add-dir"), 2)
        self.assertIn("/tmp/project-a", command)
        self.assertIn("/tmp/project-b", command)

    def test_restricted_group_command_uses_isolated_permission_profile(self) -> None:
        runner = CodexRunner(
            binary=Path("/tmp/codex"),
            profile="codex-codeshark",
            workdir=Path("/tmp/workspace"),
            restricted_workdir=Path("/tmp/group-workspace"),
            restricted_codex_home=Path("/tmp/group-codex-home"),
            timeout_seconds=60,
            model="gpt-test",
            model_reasoning_effort="xhigh",
            network_access=True,
            mcp_known_servers=("docs",),
            mcp_allowed_tools=(("docs", ("search",)),),
        )
        command = runner.build_command(
            "group question",
            None,
            ephemeral=True,
            restricted=True,
        )
        self.assertIn("/tmp/group-workspace", command)
        self.assertIn('default_permissions="codeshark_group"', command)
        self.assertIn("permissions.codeshark_group.network.enabled=false", command)
        self.assertIn("--ignore-user-config", command)
        self.assertIn("--ignore-rules", command)
        self.assertIn("--strict-config", command)
        self.assertIn("gpt-test", command)
        self.assertIn('model_reasoning_effort="xhigh"', command)
        self.assertNotIn("--sandbox", command)
        self.assertNotIn("mcp_servers.docs.enabled=false", command)
        self.assertNotIn('mcp_servers.docs.enabled_tools=["search"]', command)

    def test_restricted_group_task_cannot_resume_admin_session(self) -> None:
        with self.assertRaisesRegex(ValueError, "cannot resume"):
            self.runner.build_command("question", "thread-123", restricted=True)

    def test_restricted_child_environment_uses_isolated_codex_home(self) -> None:
        environment = self.runner._child_env(restricted=True)
        self.assertEqual(environment["CODEX_HOME"], "/tmp/group-codex-home")

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
