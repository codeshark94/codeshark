from __future__ import annotations

import json
import os
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
    def __init__(
        self,
        *,
        binary: Path,
        profile: str,
        workdir: Path,
        timeout_seconds: int,
        mcp_known_servers: tuple[str, ...] = (),
        mcp_allowed_tools: tuple[tuple[str, tuple[str, ...]], ...] = (),
    ) -> None:
        self.binary = binary
        self.profile = profile
        self.workdir = workdir
        self.timeout_seconds = timeout_seconds
        self.mcp_known_servers = mcp_known_servers
        self.mcp_allowed_tools = dict(mcp_allowed_tools)
        self._lock = threading.Lock()
        self._process: subprocess.Popen[str] | None = None
        self._cancel_requested = False

    def _mcp_config_args(self) -> list[str]:
        args: list[str] = []
        for server in self.mcp_known_servers:
            tools = self.mcp_allowed_tools.get(server)
            enabled = tools is not None
            args.extend(["-c", f"mcp_servers.{server}.enabled={str(enabled).lower()}"])
            if tools:
                encoded_tools = json.dumps(list(tools), separators=(",", ":"))
                args.extend(["-c", f"mcp_servers.{server}.enabled_tools={encoded_tools}"])
        return args

    def build_command(
        self,
        prompt: str,
        thread_id: str | None,
        *,
        ephemeral: bool = False,
    ) -> list[str]:
        base = [
            str(self.binary),
            "--profile",
            self.profile,
            "-C",
            str(self.workdir),
        ]
        base.extend(self._mcp_config_args())
        base.append("exec")
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
        env = os.environ.copy()
        env.pop("TELEGRAM_BOT_TOKEN", None)
        env["NO_COLOR"] = "1"
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
    ) -> RunResult:
        command = self.build_command(prompt, thread_id, ephemeral=ephemeral)
        env = os.environ.copy()
        env.pop("TELEGRAM_BOT_TOKEN", None)
        env["NO_COLOR"] = "1"
        with self._lock:
            self._cancel_requested = False
            self._process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=self.workdir,
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

        message, returned_thread_id = parse_codex_events(stdout)
        return RunResult(
            exit_code=process.returncode,
            message=message,
            thread_id=returned_thread_id or thread_id,
            stderr=stderr.strip(),
            cancelled=cancelled,
            timed_out=timed_out,
        )

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
