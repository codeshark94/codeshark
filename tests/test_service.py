import plistlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from codex_codeshark.automation import AgentStore
from codex_codeshark.service import (
    ServiceStatus,
    apply_deferred_restart_if_idle,
    deferred_restart_requested,
    install_service,
    read_logs,
    refresh_menu_bar,
    request_deferred_restart,
    restart_service,
    restart_when_idle,
    service_status,
)


class ServiceTests(unittest.TestCase):
    @patch("codex_codeshark.service.subprocess.run")
    def test_install_writes_private_launch_agent_and_bootstraps_it(self, run_mock: Mock) -> None:
        run_mock.return_value = Mock(returncode=0, stdout="", stderr="")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config.local.toml").write_text("configured = true\n", encoding="utf-8")
            runtime = root / "runtime"
            runtime.mkdir()
            old_log = runtime / "agent.err.log"
            old_log.write_text("old", encoding="utf-8")
            old_log.chmod(0o644)
            plist_path = root / "LaunchAgents" / "agent.plist"
            install_root = root / "Application Support" / "app"
            install_service(
                project_root=root,
                plist_path=plist_path,
                python="/usr/bin/python3",
                install_root=install_root,
            )
            with plist_path.open("rb") as stream:
                payload = plistlib.load(stream)
            menu_plist_path = plist_path.with_name("com.codeshark.status.plist")
            with menu_plist_path.open("rb") as stream:
                menu_payload = plistlib.load(stream)
            self.assertEqual(plist_path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(runtime.stat().st_mode & 0o777, 0o700)
            self.assertEqual(old_log.stat().st_mode & 0o777, 0o600)
            self.assertEqual(
                payload["ProgramArguments"],
                ["/usr/bin/python3", "-m", "codex_codeshark", "run"],
            )
            installed_source = Path(payload["EnvironmentVariables"]["PYTHONPATH"])
            self.assertTrue((installed_source / "codex_codeshark" / "__main__.py").is_file())
            self.assertTrue(installed_source.is_relative_to(install_root))
            self.assertFalse(installed_source.is_relative_to(root / "src"))
            self.assertEqual(payload["WorkingDirectory"], str(installed_source.parent))
            self.assertEqual(payload["EnvironmentVariables"]["CODEX_CODESHARK_HOME"], str(root))
            installed_config = Path(
                payload["EnvironmentVariables"]["TELEGRAM_CODEX_CONFIG"]
            )
            self.assertTrue(installed_config.is_file())
            self.assertTrue(installed_config.is_relative_to(install_root))
            self.assertEqual(payload["Umask"], 0o077)
            self.assertEqual(menu_payload["Label"], "com.codeshark.status")
            self.assertEqual(menu_payload["ProgramArguments"][1], str(root))
            self.assertTrue(menu_payload["ProgramArguments"][2].endswith("codeshark-menubar-template.png"))
            commands = [call.args[0] for call in run_mock.call_args_list]
            self.assertTrue(any("bootstrap" in command for command in commands))
            self.assertTrue(any("kickstart" in command for command in commands))

    @patch("codex_codeshark.service.subprocess.run")
    def test_refresh_menu_restarts_only_the_menu_launch_agent(self, run_mock: Mock) -> None:
        run_mock.return_value = Mock(returncode=0, stdout="", stderr="")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config.local.toml").write_text("configured = true\n", encoding="utf-8")
            (root / "runtime").mkdir()
            plist_path = root / "LaunchAgents" / "agent.plist"
            install_root = root / "Application Support" / "app"
            result = refresh_menu_bar(
                project_root=root,
                plist_path=plist_path,
                install_root=install_root,
            )
            self.assertEqual(result, plist_path.with_name("com.codeshark.status.plist"))
            commands = [call.args[0] for call in run_mock.call_args_list]
            self.assertTrue(all(str(plist_path) not in command for command in commands))
            self.assertTrue(
                any(
                    any("com.codeshark.status.plist" in str(argument) for argument in command)
                    for command in commands
                )
            )

    @patch("codex_codeshark.service.subprocess.run")
    def test_status_parses_running_pid(self, run_mock: Mock) -> None:
        run_mock.return_value = Mock(
            returncode=0,
            stdout="state = running\n\tpid = 4321\n",
            stderr="",
        )
        status = service_status()
        self.assertTrue(status.running)
        self.assertEqual((status.state, status.pid), ("running", 4321))

    def test_logs_are_bounded_and_redact_telegram_tokens(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / "runtime"
            runtime.mkdir()
            (runtime / "agent.err.log").write_text(
                "old\n123456789:ABC_def-123\nlatest\n",
                encoding="utf-8",
            )
            content = read_logs(2, project_root=root)
            self.assertNotIn("123456789:ABC_def-123", content)
            self.assertIn("[REDACTED_TELEGRAM_TOKEN]", content)
            self.assertNotIn("old", content)

    @patch("codex_codeshark.service.time.sleep")
    @patch("codex_codeshark.service.install_service")
    @patch("codex_codeshark.service.service_status")
    def test_restart_waits_through_transient_xpcproxy_state(
        self,
        status_mock: Mock,
        install_mock: Mock,
        _sleep_mock: Mock,
    ) -> None:
        status_mock.side_effect = [
            ServiceStatus(False, "xpcproxy", 456),
            ServiceStatus(True, "running", 456),
        ]
        with tempfile.TemporaryDirectory() as directory:
            plist = Path(directory) / "agent.plist"
            plist.write_text("placeholder", encoding="utf-8")
            result = restart_service(plist_path=plist)
        install_mock.assert_called_once()
        self.assertTrue(result.running)
        self.assertEqual(result.pid, 456)

    def test_deferred_restart_waits_for_the_active_task(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / "runtime"
            runtime.mkdir()
            store = AgentStore(runtime / "agent.db")
            task = store.enqueue_task(123, "work", source="telegram", ephemeral=False)
            claimed = store.claim_next_task(now=task.created_at + 1)
            self.assertEqual(claimed.id, task.id)

            request_deferred_restart(project_root=root)
            restart = Mock(return_value=ServiceStatus(True, "running", 456))
            self.assertIsNone(
                apply_deferred_restart_if_idle(project_root=root, restart=restart)
            )
            restart.assert_not_called()
            self.assertTrue(deferred_restart_requested(project_root=root))

            store.finish_task(task.id, "completed")
            result = apply_deferred_restart_if_idle(project_root=root, restart=restart)

            self.assertEqual(result, ServiceStatus(True, "running", 456))
            restart.assert_called_once_with(project_root=root)
            self.assertFalse(deferred_restart_requested(project_root=root))

    @patch("codex_codeshark.service.subprocess.Popen")
    def test_restart_when_idle_starts_a_monitor_for_active_work(self, popen_mock: Mock) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / "runtime"
            runtime.mkdir()
            store = AgentStore(runtime / "agent.db")
            task = store.enqueue_task(123, "work", source="telegram", ephemeral=False)
            store.claim_next_task(now=task.created_at + 1)

            self.assertIsNone(restart_when_idle(project_root=root))

            self.assertTrue(deferred_restart_requested(project_root=root))
            popen_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
