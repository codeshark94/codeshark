import json
import os
import subprocess
import time
from unittest.mock import Mock
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from codex_codeshark.codex_runner import (
    CodexRunner,
    RunResult,
    parse_codex_events,
    parse_token_usage,
    parse_tool_usage_item,
)


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
        self.assertIn('sandbox_mode="read-only"', command)
        self.assertIn("sandbox_workspace_write.network_access=false", command)
        self.assertNotIn("--add-dir", command)
        self.assertIn("mcp_servers.github.enabled=false", command)

    def test_zero_timeout_disables_the_runner_deadline(self) -> None:
        runner = CodexRunner(
            binary=Path("/tmp/codex"),
            profile="codex-codeshark",
            workdir=Path("/tmp/workspace"),
            timeout_seconds=0,
        )

        self.assertIsNone(runner.timeout_seconds)

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
        command = self.runner.build_command("scheduled", None, ephemeral=True, approved=True)
        self.assertIn("--ephemeral", command)
        self.assertIn("mcp_servers.github.enabled=true", command)
        self.assertIn('mcp_servers.github.enabled_tools=["list_issues"]', command)
        self.assertIn("mcp_servers.docs.enabled=false", command)

    def test_group_permission_switches_can_disable_network_and_writes(self) -> None:
        runner = CodexRunner(
            binary=Path("/tmp/codex"),
            profile="codex-codeshark",
            workdir=Path("/tmp/workspace"),
            restricted_workdir=Path("/tmp/group-workspace"),
            restricted_codex_home=Path("/tmp/group-codex-home"),
            timeout_seconds=60,
            restricted_network_access=False,
            restricted_workspace_write=False,
        )

        command = runner.build_command("summarize", None, restricted=True)

        self.assertIn('permissions.codeshark_group.filesystem={":minimal"="read",":workspace_roots"={"."="read"}}', command)
        self.assertIn("permissions.codeshark_group.network.enabled=false", command)
        self.assertIn('web_search="disabled"', command)

    def test_app_server_command_pins_configured_model(self) -> None:
        runner = CodexRunner(
            binary=Path("/tmp/codex"),
            profile="codex-codeshark",
            workdir=Path("/tmp/workspace"),
            timeout_seconds=60,
            model="gpt-5.5",
            model_reasoning_effort="high",
        )

        command = runner.build_app_server_command(approved=False, full_access=False)

        self.assertNotIn("--profile", command)
        self.assertIn('service_tier="standard"', command)
        self.assertIn('model="gpt-5.5"', command)
        self.assertIn('model_reasoning_effort="high"', command)

    def test_full_access_command_enables_explicit_figma_tools_only(self) -> None:
        runner = CodexRunner(
            binary=Path("/tmp/codex"),
            profile="codex-codeshark",
            workdir=Path("/tmp/workspace"),
            timeout_seconds=60,
            mcp_known_servers=("figma",),
            mcp_allowed_tools=(("figma", ("get_metadata", "get_screenshot")),),
        )

        command = runner.build_command("inspect a Figma design", None, full_access=True)

        self.assertIn("mcp_servers.figma.enabled=true", command)
        self.assertIn(
            'mcp_servers.figma.enabled_tools=["get_metadata","get_screenshot"]',
            command,
        )

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

    def test_steer_writes_a_turn_steer_request_for_an_active_app_server_turn(self) -> None:
        process = Mock()
        process.poll.return_value = None
        process.stdin = Mock()
        self.runner._process = process
        self.runner._active_thread_id = "thread-1"
        self.runner._active_turn_id = "turn-1"
        self.runner._turn_steerable = True

        self.assertTrue(self.runner.steer("focus on tests"))

        payload = process.stdin.write.call_args.args[0]
        self.assertIn('"method":"turn/steer"', payload)
        self.assertIn('"expectedTurnId":"turn-1"', payload)
        self.assertIn('focus on tests', payload)

    def test_retries_app_server_after_rejected_tool_timeout(self) -> None:
        rejected = SimpleNamespace(
            exit_code=1,
            message="",
            thread_id="thread-1",
            stderr="Codex turn did not complete\ntimeout_ms must be at least 10000",
            cancelled=False,
            timed_out=False,
        )
        completed = SimpleNamespace(
            exit_code=0,
            message="done",
            thread_id="thread-1",
            stderr="",
            cancelled=False,
            timed_out=False,
        )
        with patch.object(
            self.runner,
            "_run_app_server",
            side_effect=[rejected, completed],
        ) as run:
            result = self.runner.run("repair the figure", None)

        self.assertEqual(result, completed)
        self.assertEqual(run.call_count, 2)
        retry_prompt, retry_thread_id = run.call_args.args[:2]
        self.assertEqual(retry_thread_id, "thread-1")
        self.assertIn("timeout_ms", retry_prompt)
        self.assertIn("10000", retry_prompt)

    def test_retries_transient_app_server_failure_before_turn_start(self) -> None:
        rejected = RunResult(
            exit_code=1,
            message="",
            thread_id=None,
            stderr="HTTP 451: no_biscuit_no_service",
        )
        completed = RunResult(
            exit_code=0,
            message="done",
            thread_id="thread-1",
            stderr="",
            turn_started=True,
        )
        with patch.object(
            self.runner,
            "_run_app_server",
            side_effect=[rejected, completed],
        ) as run:
            result = self.runner.run("repair the figure", None)

        self.assertEqual(run.call_count, 2)
        self.assertEqual(run.call_args.args[:2], ("repair the figure", None))
        self.assertTrue(result.startup_retried)
        self.assertEqual(result.message, "done")

    def test_rolls_over_oversized_persistent_session_before_turn_start(self) -> None:
        rejected = RunResult(
            exit_code=1,
            message="",
            thread_id="thread-old",
            stderr="Codex app-server returned an oversized protocol message",
        )
        completed = RunResult(
            exit_code=0,
            message="done",
            thread_id="thread-new",
            stderr="",
            turn_started=True,
        )
        with patch.object(
            self.runner,
            "_run_app_server",
            side_effect=[rejected, completed],
        ) as run:
            result = self.runner.run("continue the figure revision", "thread-old")

        self.assertEqual(run.call_count, 2)
        retry_prompt, retry_thread_id = run.call_args.args[:2]
        self.assertIsNone(retry_thread_id)
        self.assertIn("project-session rollover", retry_prompt)
        self.assertTrue(result.startup_retried)
        self.assertEqual(result.thread_id, "thread-new")

    def test_does_not_roll_over_oversized_session_after_turn_start(self) -> None:
        failed = RunResult(
            exit_code=1,
            message="",
            thread_id="thread-old",
            stderr="Codex app-server returned an oversized protocol message",
            turn_started=True,
        )
        with patch.object(self.runner, "_run_app_server", return_value=failed) as run:
            result = self.runner.run("continue the figure revision", "thread-old")

        self.assertIs(result, failed)
        self.assertEqual(run.call_count, 1)

    def test_does_not_retry_transient_failure_after_turn_start(self) -> None:
        failed = RunResult(
            exit_code=1,
            message="",
            thread_id="thread-1",
            stderr="HTTP 451: no_biscuit_no_service",
            turn_started=True,
        )
        with patch.object(self.runner, "_run_app_server", return_value=failed) as run:
            result = self.runner.run("repair the figure", None)

        self.assertIs(result, failed)
        self.assertEqual(run.call_count, 1)

    def test_retries_ephemeral_run_after_rejected_tool_timeout(self) -> None:
        rejected = SimpleNamespace(
            exit_code=1,
            message="",
            thread_id="thread-1",
            stderr="timeout_ms must be at least 10000",
            cancelled=False,
            timed_out=False,
        )
        completed = SimpleNamespace(
            exit_code=0,
            message="done",
            thread_id="thread-1",
            stderr="",
            cancelled=False,
            timed_out=False,
        )
        with patch.object(
            self.runner,
            "_run_exec",
            side_effect=[rejected, completed],
        ) as run:
            result = self.runner.run("validate", None, ephemeral=True)

        self.assertEqual(result, completed)
        self.assertEqual(run.call_count, 2)
        retry_prompt, retry_thread_id = run.call_args.args[:2]
        self.assertEqual(retry_thread_id, "thread-1")
        self.assertIn("timeout_ms", retry_prompt)

    def test_app_server_reader_keeps_buffered_protocol_messages(self) -> None:
        read_descriptor, write_descriptor = os.pipe()
        stream = os.fdopen(read_descriptor, "r", encoding="utf-8")
        process = SimpleNamespace(stdout=stream)
        try:
            os.write(write_descriptor, b'{"method":"first"}\n{"method":"second"}\n')
            deadline = time.monotonic() + 1

            first = self.runner._read_server_message(process, deadline)
            second = self.runner._read_server_message(process, deadline)

            self.assertEqual(first, {"method": "first"})
            self.assertEqual(second, {"method": "second"})
        finally:
            os.close(write_descriptor)
            stream.close()

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
            runner.build_command("hello", None, approved=True),
        )

    def test_delegated_project_roots_are_added_to_admin_sandbox(self) -> None:
        runner = CodexRunner(
            binary=Path("/tmp/codex"),
            profile="codex-codeshark",
            workdir=Path("/tmp/workspace"),
            timeout_seconds=60,
            additional_write_roots=(Path("/tmp/project-a"), Path("/tmp/project-b")),
        )
        command = runner.build_command("work across projects", None, approved=True)
        self.assertEqual(command.count("--add-dir"), 2)
        self.assertIn("/tmp/project-a", command)
        self.assertIn("/tmp/project-b", command)

    def test_unapproved_task_cannot_receive_mutating_capabilities(self) -> None:
        runner = CodexRunner(
            binary=Path("/tmp/codex"),
            profile="codex-codeshark",
            workdir=Path("/tmp/workspace"),
            timeout_seconds=60,
            additional_write_roots=(Path("/tmp/project-a"),),
            network_access=True,
            mcp_known_servers=("github",),
            mcp_allowed_tools=(("github", ("mutate_repository",)),),
        )
        command = runner.build_command("inspect untrusted content", None, approved=False)
        self.assertIn('sandbox_mode="read-only"', command)
        self.assertIn("sandbox_workspace_write.network_access=false", command)
        self.assertIn("mcp_servers.github.enabled=false", command)
        self.assertNotIn("--add-dir", command)
        self.assertNotIn("mutate_repository", command)

        approved = runner.build_command("apply approved change", None, approved=True)
        self.assertNotIn('sandbox_mode="read-only"', approved)
        self.assertIn("sandbox_workspace_write.network_access=true", approved)
        self.assertIn("mcp_servers.github.enabled=true", approved)
        self.assertTrue(any("mutate_repository" in argument for argument in approved))
        self.assertIn("--add-dir", approved)

    def test_full_access_command_keeps_unallowlisted_mcp_servers_disabled(self) -> None:
        runner = CodexRunner(
            binary=Path("/tmp/codex"),
            profile="codex-codeshark",
            workdir=Path("/tmp/workspace"),
            timeout_seconds=60,
            mcp_known_servers=("computer-use",),
        )
        command = runner.build_command("install a plugin", None, full_access=True)
        self.assertIn('sandbox_mode="danger-full-access"', command)
        self.assertIn('approval_policy="never"', command)
        self.assertIn('web_search="live"', command)
        self.assertIn("features.computer_use=true", command)
        self.assertIn("mcp_servers.computer-use.enabled=false", command)
        self.assertNotIn('sandbox_mode="read-only"', command)

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
        self.assertIn('permissions.codeshark_group.filesystem={":minimal"="read",":workspace_roots"={"."="write"}}', command)
        self.assertIn("permissions.codeshark_group.network.enabled=true", command)
        self.assertIn('web_search="live"', command)
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

    def test_admin_child_environment_uses_private_codeshark_home(self) -> None:
        runner = CodexRunner(
            binary=Path("/tmp/codex"),
            profile="codex-codeshark",
            workdir=Path("/tmp/workspace"),
            codex_home=Path("/tmp/codeshark-codex-home"),
            timeout_seconds=60,
        )

        self.assertEqual(
            runner._child_env()["CODEX_HOME"],
            "/tmp/codeshark-codex-home",
        )

    def test_restricted_workspace_is_cleared_after_a_group_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            (workspace / "report.md").write_text("temporary", encoding="utf-8")
            nested = workspace / "repository"
            nested.mkdir()
            (nested / "notes.txt").write_text("temporary", encoding="utf-8")
            runner = CodexRunner(
                binary=Path("/tmp/codex"),
                profile="codex-codeshark",
                workdir=Path("/tmp/workspace"),
                restricted_workdir=workspace,
                restricted_codex_home=Path("/tmp/group-codex-home"),
                timeout_seconds=60,
            )

            runner._cleanup_restricted_workspace()

            self.assertEqual(list(workspace.iterdir()), [])

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

    def test_parses_exact_token_usage_breakdown(self) -> None:
        usage = parse_token_usage(
            {
                "inputTokens": 100,
                "cachedInputTokens": 20,
                "cacheWriteInputTokens": 5,
                "outputTokens": 30,
                "reasoningOutputTokens": 10,
                "totalTokens": 130,
            }
        )

        self.assertIsNotNone(usage)
        self.assertEqual(usage.input_tokens, 100)
        self.assertEqual(usage.cached_input_tokens, 20)
        self.assertEqual(usage.cache_write_input_tokens, 5)
        self.assertEqual(usage.output_tokens, 30)
        self.assertEqual(usage.reasoning_output_tokens, 10)
        self.assertEqual(usage.total_tokens, 130)

    def test_rejects_incomplete_token_usage_breakdown(self) -> None:
        self.assertIsNone(parse_token_usage({"inputTokens": 100}))

    def test_recognizes_completed_tool_item_types(self) -> None:
        self.assertEqual(
            parse_tool_usage_item({"type": "webSearch"}),
            "web_search_calls",
        )
        self.assertEqual(
            parse_tool_usage_item({"type": "mcpToolCall"}),
            "mcp_tool_calls",
        )
        self.assertIsNone(parse_tool_usage_item({"type": "agentMessage"}))


if __name__ == "__main__":
    unittest.main()
