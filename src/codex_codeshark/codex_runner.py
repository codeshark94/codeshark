from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RunResult:
    exit_code: int
    message: str
    thread_id: str | None
    stderr: str
    cancelled: bool = False
    timed_out: bool = False


def parse_codex_events(output: str) -> tuple[str, str | None]:
    messages: list[str] = []
    thread_id: str | None = None
    for raw_line in output.splitlines():
        try:
            event: dict[str, Any] = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "thread.started" and isinstance(event.get("thread_id"), str):
            thread_id = event["thread_id"]
        if event.get("type") != "item.completed":
            continue
        item = event.get("item")
        if isinstance(item, dict) and item.get("type") == "agent_message":
            text = item.get("text")
            if isinstance(text, str) and text.strip():
                messages.append(text.strip())
    return (messages[-1] if messages else ""), thread_id


class CodexRunner:
    _CHILD_ENV_ALLOWLIST = {
        "CODEX_HOME",
        "HOME",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "LOGNAME",
        "PATH",
        "SSL_CERT_DIR",
        "SSL_CERT_FILE",
        "TMPDIR",
        "USER",
    }

    def __init__(
        self,
        *,
        binary: Path,
        profile: str,
        workdir: Path,
        restricted_workdir: Path | None = None,
        restricted_codex_home: Path | None = None,
        timeout_seconds: int,
        model: str | None = None,
        model_reasoning_effort: str | None = None,
        additional_write_roots: tuple[Path, ...] = (),
        mcp_known_servers: tuple[str, ...] = (),
        mcp_allowed_tools: tuple[tuple[str, tuple[str, ...]], ...] = (),
        network_access: bool = False,
    ) -> None:
        self.binary = binary
        self.profile = profile
        self.workdir = workdir
        self.restricted_workdir = restricted_workdir or workdir
        self.restricted_codex_home = restricted_codex_home
        self.timeout_seconds = timeout_seconds
        self.model = model
        self.model_reasoning_effort = model_reasoning_effort
        self.additional_write_roots = additional_write_roots
        self.mcp_known_servers = mcp_known_servers
        self.mcp_allowed_tools = dict(mcp_allowed_tools)
        self.network_access = network_access
        self._lock = threading.Lock()
        self._process: subprocess.Popen[str] | None = None
        self._cancel_requested = False

    def _mcp_config_args(self, *, restricted: bool = False) -> list[str]:
        args: list[str] = []
        for server in self.mcp_known_servers:
            tools = None if restricted else self.mcp_allowed_tools.get(server)
            enabled = tools is not None
            args.extend(["-c", f"mcp_servers.{server}.enabled={str(enabled).lower()}"])
            if tools:
                encoded_tools = json.dumps(list(tools), separators=(",", ":"))
                args.extend(["-c", f"mcp_servers.{server}.enabled_tools={encoded_tools}"])
        return args

    def _child_env(self, *, restricted: bool = False) -> dict[str, str]:
        env = {
            key: value
            for key, value in os.environ.items()
            if key in self._CHILD_ENV_ALLOWLIST
        }
        env.setdefault("HOME", str(Path.home()))
        env.setdefault("PATH", "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin")
        if restricted:
            if self.restricted_codex_home is None:
                raise RuntimeError("restricted Codex home is not configured")
            env["CODEX_HOME"] = str(self.restricted_codex_home)
        env["NO_COLOR"] = "1"
        return env

    def _restricted_config_args(self) -> list[str]:
        filesystem = '{":minimal"="read",":workspace_roots"={"."="read"}}'
        args = [
            "-c",
            'default_permissions="codeshark_group"',
            "-c",
            'permissions.codeshark_group.description="Isolated Telegram group request"',
            "-c",
            f"permissions.codeshark_group.filesystem={filesystem}",
            "-c",
            "permissions.codeshark_group.network.enabled=false",
            "-c",
            'approval_policy="never"',
            "-c",
            'web_search="disabled"',
            "-c",
            "features.apps=false",
            "-c",
            "features.browser_use=false",
            "-c",
            "features.computer_use=false",
            "-c",
            "features.image_generation=false",
            "-c",
            "features.memories=false",
            "-c",
            "features.multi_agent=false",
            "-c",
            "features.tool_suggest=false",
            "-c",
            "project_doc_max_bytes=0",
        ]
        if self.model:
            args.extend(["--model", self.model])
        if self.model_reasoning_effort:
            encoded = json.dumps(self.model_reasoning_effort)
            args.extend(["-c", f"model_reasoning_effort={encoded}"])
        return args

    def build_command(
        self,
        prompt: str,
        thread_id: str | None,
        *,
        ephemeral: bool = False,
        restricted: bool = False,
    ) -> list[str]:
        if restricted:
            if thread_id is not None:
                raise ValueError("restricted group tasks cannot resume a Codex session")
            base = [
                str(self.binary),
                "-C",
                str(self.restricted_workdir),
                *self._restricted_config_args(),
                "exec",
                "--ignore-user-config",
                "--ignore-rules",
                "--strict-config",
                "--ephemeral",
                "--json",
                "--skip-git-repo-check",
                prompt,
            ]
            return base

        base = [
            str(self.binary),
            "--profile",
            self.profile,
            "-C",
            str(self.workdir),
        ]
        for root in self.additional_write_roots:
            base.extend(["--add-dir", str(root)])
        if self.model:
            base.extend(["--model", self.model])
        if self.model_reasoning_effort:
            encoded = json.dumps(self.model_reasoning_effort)
            base.extend(["-c", f"model_reasoning_effort={encoded}"])
        base.extend(
            [
                "-c",
                "sandbox_workspace_write.network_access=" + str(self.network_access).lower(),
                *self._mcp_config_args(),
                "exec",
            ]
        )
        if thread_id:
            flags = ["resume"]
            if ephemeral:
                flags.append("--ephemeral")
            return base + flags + ["--json", "--skip-git-repo-check", thread_id, prompt]
        flags = ["--ephemeral"] if ephemeral else []
        return base + flags + ["--json", "--skip-git-repo-check", prompt]

    def build_delete_command(self, thread_id: str) -> list[str]:
        return [
            str(self.binary),
            "--profile",
            self.profile,
            "-C",
            str(self.workdir),
            "delete",
            "--force",
            thread_id,
        ]

    def delete_session(self, thread_id: str) -> None:
        env = self._child_env()
        try:
            result = subprocess.run(
                self.build_delete_command(thread_id),
                capture_output=True,
                text=True,
                cwd=self.workdir,
                env=env,
                timeout=30,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("Codex session deletion timed out") from exc
        if result.returncode != 0:
            details = result.stderr.strip()[-500:] or "unknown Codex delete error"
            raise RuntimeError(details)

    def run(
        self,
        prompt: str,
        thread_id: str | None,
        *,
        ephemeral: bool = False,
        restricted: bool = False,
    ) -> RunResult:
        command = self.build_command(
            prompt,
            thread_id,
            ephemeral=ephemeral,
            restricted=restricted,
        )
        env = self._child_env(restricted=restricted)
        run_workdir = self.restricted_workdir if restricted else self.workdir
        with self._lock:
            self._cancel_requested = False
            self._process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=run_workdir,
                env=env,
                start_new_session=True,
            )
            process = self._process

        timed_out = False
        try:
            stdout, stderr = process.communicate(timeout=self.timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            self._terminate(process)
            stdout, stderr = process.communicate()
        finally:
            with self._lock:
                cancelled = self._cancel_requested
                self._process = None
            if restricted:
                self._cleanup_restricted_home()

        message, returned_thread_id = parse_codex_events(stdout)
        return RunResult(
            exit_code=process.returncode,
            message=message,
            thread_id=returned_thread_id or thread_id,
            stderr=stderr.strip(),
            cancelled=cancelled,
            timed_out=timed_out,
        )

    def _cleanup_restricted_home(self) -> None:
        if self.restricted_codex_home is None or not self.restricted_codex_home.is_dir():
            return
        retained = {"auth.json", "cache", "installation_id", "models_cache.json", "plugins", "skills"}
        for path in self.restricted_codex_home.iterdir():
            if path.name in retained:
                continue
            try:
                if path.is_dir() and not path.is_symlink():
                    shutil.rmtree(path)
                else:
                    path.unlink(missing_ok=True)
            except OSError:
                pass

    def cancel(self) -> bool:
        with self._lock:
            process = self._process
            if process is None or process.poll() is not None:
                return False
            self._cancel_requested = True
            self._terminate(process)
            return True

    @staticmethod
    def _terminate(process: subprocess.Popen[str]) -> None:
        if process.poll() is not None:
            return
        try:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=5)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
