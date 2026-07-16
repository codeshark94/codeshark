import plistlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from codex_codeshark.service import (
    ServiceStatus,
    install_service,
    read_logs,
    restart_service,
    service_status,
)


class ServiceTests(unittest.TestCase):
    @patch("codex_codeshark.service.subprocess.run")
    def test_install_writes_private_launch_agent_and_bootstraps_it(self, run_mock: Mock) -> None:
        run_mock.return_value = Mock(returncode=0, stdout="", stderr="")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config.local.toml").write_text("configured = true\n", encoding="utf-8")
            plist_path = root / "LaunchAgents" / "agent.plist"
            install_service(
                project_root=root,
                plist_path=plist_path,
                python="/usr/bin/python3",
            )
            with plist_path.open("rb") as stream:
                payload = plistlib.load(stream)
            self.assertEqual(plist_path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(
                payload["ProgramArguments"],
                ["/usr/bin/python3", "-m", "codex_codeshark", "run"],
            )
            commands = [call.args[0] for call in run_mock.call_args_list]
            self.assertTrue(any("bootstrap" in command for command in commands))
            self.assertTrue(any("kickstart" in command for command in commands))

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
    @patch("codex_codeshark.service.subprocess.run")
    @patch("codex_codeshark.service.service_status")
    def test_restart_waits_through_transient_xpcproxy_state(
        self,
        status_mock: Mock,
        run_mock: Mock,
        _sleep_mock: Mock,
    ) -> None:
        running = ServiceStatus(True, "running", 123)
        status_mock.side_effect = [
            running,
            ServiceStatus(False, "xpcproxy", 456),
            ServiceStatus(True, "running", 456),
        ]
        run_mock.return_value = Mock(returncode=0, stdout="", stderr="")
        with tempfile.TemporaryDirectory() as directory:
            plist = Path(directory) / "agent.plist"
            plist.write_text("placeholder", encoding="utf-8")
            result = restart_service(plist_path=plist)
        self.assertTrue(result.running)
        self.assertEqual(result.pid, 456)


if __name__ == "__main__":
    unittest.main()
