from __future__ import annotations

import json
import os
import re
import select
import shutil
import signal
import subprocess
import threading
import time
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
    token_usage: "TokenUsage | None" = None


@dataclass(frozen=True)
class TokenUsage:
    """Exact token totals emitted by Codex for one completed turn."""

    input_tokens: int
    cached_input_tokens: int
    cache_write_input_tokens: int
    output_tokens: int
    reasoning_output_tokens: int
    total_tokens: int


@dataclass(frozen=True)
class RateLimitWindow:
    used_percent: int
    resets_at: int | None
    window_duration_mins: int | None


@dataclass(frozen=True)
class AccountUsageBucket:
    limit_id: str
    limit_name: str | None
    primary: RateLimitWindow | None
    secondary: RateLimitWindow | None


@dataclass(frozen=True)
class AccountUsageSnapshot:
    observed_at: float
    buckets: tuple[AccountUsageBucket, ...]


def parse_token_usage(value: object) -> TokenUsage | None:
    """Parse Codex's documented token-usage breakdown without guessing fields."""
    if not isinstance(value, dict):
        return None
    required = (
        "inputTokens",
        "cachedInputTokens",
        "cacheWriteInputTokens",
        "outputTokens",
        "reasoningOutputTokens",
        "totalTokens",
    )
    if not all(isinstance(value.get(field), int) for field in required):
        return None
    return TokenUsage(
        input_tokens=value["inputTokens"],
        cached_input_tokens=value["cachedInputTokens"],
        cache_write_input_tokens=value["cacheWriteInputTokens"],
        output_tokens=value["outputTokens"],
        reasoning_output_tokens=value["reasoningOutputTokens"],
        total_tokens=value["totalTokens"],
    )


def _parse_rate_limit_window(value: object) -> RateLimitWindow | None:
    if not isinstance(value, dict) or not isinstance(value.get("usedPercent"), int):
        return None
    resets_at = value.get("resetsAt")
    duration = value.get("windowDurationMins")
    return RateLimitWindow(
        used_percent=value["usedPercent"],
        resets_at=resets_at if isinstance(resets_at, int) else None,
        window_duration_mins=duration if isinstance(duration, int) else None,
    )


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
    _TOOL_TIMEOUT_VALIDATION_ERROR = re.compile(
        r"timeout_ms must be at least 10000", re.IGNORECASE
    )
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
        role: str = "Unassigned",
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
        self.role = role
        self.additional_write_roots = additional_write_roots
        self.mcp_known_servers = mcp_known_servers
        self.mcp_allowed_tools = dict(mcp_allowed_tools)
        self.network_access = network_access
        self._lock = threading.Lock()
        self._process: subprocess.Popen[str] | None = None
        self._cancel_requested = False
        self._active_thread_id: str | None = None
        self._active_turn_id: str | None = None
        self._turn_steerable = False
        self._pending_steers: list[str] = []
        self._next_rpc_id = 10
        self._server_read_buffer = b""

    def _mcp_config_args(
        self,
        *,
        restricted: bool = False,
    ) -> list[str]:
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
        filesystem = '{":minimal"="read",":workspace_roots"={"."="write"}}'
        args = [
            "-c",
            'default_permissions="codeshark_group"',
            "-c",
            'permissions.codeshark_group.description="Isolated Telegram group request"',
            "-c",
            f"permissions.codeshark_group.filesystem={filesystem}",
            "-c",
            "permissions.codeshark_group.network.enabled=true",
            "-c",
            'approval_policy="never"',
            "-c",
            'web_search="live"',
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

    def _unapproved_config_args(self) -> list[str]:
        return [
            "-c",
            'sandbox_mode="read-only"',
            "-c",
            "sandbox_workspace_write.network_access=false",
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
            *self._mcp_config_args(restricted=True),
        ]

    def _full_access_config_args(self) -> list[str]:
        return [
            "-c",
            'sandbox_mode="danger-full-access"',
            "-c",
            'approval_policy="never"',
            "-c",
            'web_search="live"',
            "-c",
            "features.apps=true",
            "-c",
            "features.browser_use=true",
            "-c",
            "features.computer_use=true",
            "-c",
            "features.image_generation=true",
            "-c",
            "features.memories=true",
            "-c",
            "features.multi_agent=true",
            "-c",
            "features.tool_suggest=true",
            *self._mcp_config_args(),
        ]

    def build_command(
        self,
        prompt: str,
        thread_id: str | None,
        *,
        ephemeral: bool = False,
        restricted: bool = False,
        approved: bool = False,
        full_access: bool = False,
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
        if approved or full_access:
            for root in self.additional_write_roots:
                base.extend(["--add-dir", str(root)])
        if self.model:
            base.extend(["--model", self.model])
        if self.model_reasoning_effort:
            encoded = json.dumps(self.model_reasoning_effort)
            base.extend(["-c", f"model_reasoning_effort={encoded}"])
        if full_access:
            base.extend(self._full_access_config_args())
        elif approved:
            base.extend(
                [
                    "-c",
                    "sandbox_workspace_write.network_access="
                    + str(self.network_access).lower(),
                    *self._mcp_config_args(),
                ]
            )
        else:
            base.extend(self._unapproved_config_args())
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

    def build_app_server_command(
        self,
        *,
        approved: bool,
        full_access: bool,
    ) -> list[str]:
        command = [str(self.binary), "-C", str(self.workdir)]
        command.extend(["-c", 'service_tier="standard"'])
        if self.model:
            command.extend(["-c", f"model={json.dumps(self.model)}"])
        if self.model_reasoning_effort:
            encoded = json.dumps(self.model_reasoning_effort)
            command.extend(["-c", f"model_reasoning_effort={encoded}"])
        if full_access:
            command.extend(self._full_access_config_args())
        elif approved:
            command.extend(
                [
                    "-c",
                    "sandbox_workspace_write.network_access="
                    + str(self.network_access).lower(),
                    *self._mcp_config_args(),
                ]
            )
        else:
            command.extend(self._unapproved_config_args())
        return [*command, "app-server", "--stdio", "--strict-config"]

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

    def read_account_usage(self, *, timeout_seconds: int = 20) -> AccountUsageSnapshot:
        """Read Codex's live, account-level rate-limit state without starting a turn."""
        process = subprocess.Popen(
            self.build_app_server_command(approved=False, full_access=False),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=self.workdir,
            env=self._child_env(),
            start_new_session=True,
        )
        deadline = time.monotonic() + timeout_seconds
        read_buffer = b""
        request_id = 0

        def request(method: str, params: object) -> dict[str, object]:
            nonlocal read_buffer, request_id
            request_id += 1
            self._write_server_message(
                process, {"method": method, "id": request_id, "params": params}
            )
            while True:
                message = self._read_server_message_with_buffer(process, deadline, read_buffer)
                if message is None:
                    raise RuntimeError(f"Codex usage read timed out during {method}")
                read_buffer = message[1]
                payload = message[0]
                if payload.get("id") == request_id:
                    return payload

        try:
            initialized = request(
                "initialize",
                {
                    "clientInfo": {
                        "name": "codeshark",
                        "title": "Codeshark usage monitor",
                        "version": "0.1.0",
                    }
                },
            )
            if "error" in initialized:
                raise RuntimeError(self._server_error(initialized))
            self._write_server_message(process, {"method": "initialized", "params": {}})
            response = request("account/rateLimits/read", None)
            if "error" in response:
                raise RuntimeError(self._server_error(response))
            result = response.get("result")
            if not isinstance(result, dict):
                raise RuntimeError("Codex usage read returned no rate-limit snapshot")
            raw_buckets = result.get("rateLimitsByLimitId")
            if not isinstance(raw_buckets, dict):
                raw_buckets = {"codex": result.get("rateLimits")}
            buckets: list[AccountUsageBucket] = []
            for limit_id, value in raw_buckets.items():
                if not isinstance(limit_id, str) or not isinstance(value, dict):
                    continue
                limit_name = value.get("limitName")
                buckets.append(
                    AccountUsageBucket(
                        limit_id=limit_id,
                        limit_name=limit_name if isinstance(limit_name, str) else None,
                        primary=_parse_rate_limit_window(value.get("primary")),
                        secondary=_parse_rate_limit_window(value.get("secondary")),
                    )
                )
            if not buckets:
                raise RuntimeError("Codex usage read returned no rate-limit buckets")
            return AccountUsageSnapshot(observed_at=time.time(), buckets=tuple(buckets))
        finally:
            self._terminate(process)

    @staticmethod
    def _read_server_message_with_buffer(
        process: subprocess.Popen[str],
        deadline: float,
        read_buffer: bytes,
    ) -> tuple[dict[str, object], bytes] | None:
        if process.stdout is None:
            raise RuntimeError("Codex app-server stdout is unavailable")
        while b"\n" not in read_buffer:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            ready, _, _ = select.select([process.stdout.fileno()], [], [], remaining)
            if not ready:
                return None
            chunk = os.read(process.stdout.fileno(), 64 * 1024)
            if not chunk:
                raise RuntimeError("Codex app-server closed its protocol stream")
            read_buffer += chunk
            if len(read_buffer) > 2_000_000:
                raise RuntimeError("Codex app-server returned an oversized protocol message")
        raw_line, _, read_buffer = read_buffer.partition(b"\n")
        try:
            message = json.loads(raw_line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("Codex app-server returned invalid JSON") from exc
        if not isinstance(message, dict):
            raise RuntimeError("Codex app-server returned an invalid protocol message")
        return message, read_buffer

    def run(
        self,
        prompt: str,
        thread_id: str | None,
        *,
        ephemeral: bool = False,
        restricted: bool = False,
        approved: bool = False,
        full_access: bool = False,
    ) -> RunResult:
        if not ephemeral and not restricted:
            result = self._run_app_server(
                prompt,
                thread_id,
                approved=approved,
                full_access=full_access,
            )
            if not self._requires_timeout_retry(result):
                return result
            return self._run_app_server(
                self._timeout_retry_prompt(prompt, resumed=result.thread_id is not None),
                result.thread_id,
                approved=approved,
                full_access=full_access,
            )
        result = self._run_exec(
            prompt,
            thread_id,
            ephemeral=ephemeral,
            restricted=restricted,
            approved=approved,
            full_access=full_access,
        )
        if not self._requires_timeout_retry(result):
            return result
        retry_thread_id = None if restricted else result.thread_id
        return self._run_exec(
            self._timeout_retry_prompt(prompt, resumed=retry_thread_id is not None),
            retry_thread_id,
            ephemeral=ephemeral,
            restricted=restricted,
            approved=approved,
            full_access=full_access,
        )

    @classmethod
    def _requires_timeout_retry(cls, result: RunResult) -> bool:
        return (
            result.exit_code != 0
            and not result.cancelled
            and not result.timed_out
            and bool(cls._TOOL_TIMEOUT_VALIDATION_ERROR.search(result.stderr))
        )

    @staticmethod
    def _timeout_retry_prompt(prompt: str, *, resumed: bool) -> str:
        recovery = (
            "[Codeshark recovery]\n"
            "The preceding turn stopped because a tool call used timeout_ms below the 10000 ms "
            "minimum. That rejected call did not run. Continue from the existing workspace and "
            "thread state without repeating completed work or an external side effect. When using a "
            "tool, omit timeout_ms or set it to at least 10000. Complete the requested task.\n"
            "[/Codeshark recovery]"
        )
        return recovery if resumed else f"{prompt}\n\n{recovery}"

    def _run_exec(
        self,
        prompt: str,
        thread_id: str | None,
        *,
        ephemeral: bool = False,
        restricted: bool = False,
        approved: bool = False,
        full_access: bool = False,
    ) -> RunResult:
        command = self.build_command(
            prompt,
            thread_id,
            ephemeral=ephemeral,
            restricted=restricted,
            approved=approved,
            full_access=full_access,
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
                self._cleanup_restricted_workspace()

        message, returned_thread_id = parse_codex_events(stdout)
        return RunResult(
            exit_code=process.returncode,
            message=message,
            thread_id=returned_thread_id or thread_id,
            stderr=stderr.strip(),
            cancelled=cancelled,
            timed_out=timed_out,
        )

    def _run_app_server(
        self,
        prompt: str,
        thread_id: str | None,
        *,
        approved: bool,
        full_access: bool,
    ) -> RunResult:
        command = self.build_app_server_command(approved=approved, full_access=full_access)
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=self.workdir,
            env=self._child_env(),
            start_new_session=True,
        )
        deadline = time.monotonic() + self.timeout_seconds
        active_thread_id = thread_id
        messages: list[str] = []
        streamed_message = ""
        token_usage: TokenUsage | None = None
        timed_out = False
        exit_code = 1
        error_message = ""
        with self._lock:
            self._cancel_requested = False
            self._process = process
            self._active_thread_id = thread_id
            self._active_turn_id = None
            self._turn_steerable = False
            self._pending_steers = []
            self._server_read_buffer = b""
        try:
            initialized = self._server_request(
                process,
                "initialize",
                {
                    "clientInfo": {
                        "name": "codeshark",
                        "title": "Codeshark",
                        "version": "0.1.0",
                    }
                },
                deadline,
            )
            if "error" in initialized:
                error_message = self._server_error(initialized)
                return RunResult(1, "", active_thread_id, error_message)
            self._server_notify(process, "initialized", {})
            if active_thread_id:
                thread_response = self._server_request(
                    process,
                    "thread/resume",
                    {"threadId": active_thread_id, "cwd": str(self.workdir)},
                    deadline,
                )
            else:
                thread_response = self._server_request(
                    process,
                    "thread/start",
                    {"cwd": str(self.workdir), "model": self.model},
                    deadline,
                )
            if "error" in thread_response:
                error_message = self._server_error(thread_response)
                return RunResult(1, "", active_thread_id, error_message)
            returned_thread = thread_response.get("result", {}).get("thread", {}).get("id")
            if isinstance(returned_thread, str):
                active_thread_id = returned_thread
            if not active_thread_id:
                return RunResult(1, "", None, "Codex app-server did not return a thread ID")
            with self._lock:
                self._active_thread_id = active_thread_id
            turn_response = self._server_request(
                process,
                "turn/start",
                {
                    "threadId": active_thread_id,
                    "input": [{"type": "text", "text": prompt}],
                    "cwd": str(self.workdir),
                    "approvalPolicy": "never",
                    "sandboxPolicy": self._app_server_sandbox(
                        approved=approved,
                        full_access=full_access,
                    ),
                    "model": self.model,
                    "effort": self.model_reasoning_effort,
                },
                deadline,
            )
            if "error" in turn_response:
                error_message = self._server_error(turn_response)
                return RunResult(1, "", active_thread_id, error_message)
            returned_turn = turn_response.get("result", {}).get("turn", {}).get("id")
            if not isinstance(returned_turn, str):
                return RunResult(1, "", active_thread_id, "Codex app-server did not return a turn ID")
            with self._lock:
                self._active_turn_id = returned_turn

            while True:
                event = self._read_server_message(process, deadline)
                if event is None:
                    timed_out = True
                    error_message = "Codex app-server timed out"
                    break
                method = event.get("method")
                params = event.get("params")
                if method == "turn/started" and isinstance(params, dict):
                    turn = params.get("turn")
                    started_turn = turn.get("id") if isinstance(turn, dict) else None
                    if started_turn == returned_turn:
                        with self._lock:
                            self._turn_steerable = True
                        self._flush_pending_steers(process)
                elif method == "item/completed" and isinstance(params, dict):
                    item = params.get("item")
                    if isinstance(item, dict) and item.get("type") in {
                        "agentMessage",
                        "agent_message",
                    }:
                        text = item.get("text")
                        if isinstance(text, str) and text.strip():
                            messages.append(text.strip())
                elif method == "item/agentMessage/delta" and isinstance(params, dict):
                    delta = params.get("delta")
                    if isinstance(delta, str):
                        streamed_message += delta
                elif method == "thread/tokenUsage/updated" and isinstance(params, dict):
                    usage = params.get("tokenUsage")
                    if isinstance(usage, dict):
                        token_usage = parse_token_usage(usage.get("last"))
                elif method == "turn/completed" and isinstance(params, dict):
                    turn = params.get("turn")
                    status = turn.get("status") if isinstance(turn, dict) else "failed"
                    if status == "completed":
                        exit_code = 0
                    else:
                        error = turn.get("error") if isinstance(turn, dict) else None
                        error_message = (
                            error.get("message", "Codex turn did not complete")
                            if isinstance(error, dict)
                            else "Codex turn did not complete"
                        )
                    with self._lock:
                        self._turn_steerable = False
                    break
        except (BrokenPipeError, OSError, RuntimeError, ValueError) as exc:
            error_message = str(exc) or "Codex app-server failed"
        finally:
            self._terminate(process)
            stderr = process.stderr.read().strip() if process.stderr is not None else ""
            with self._lock:
                cancelled = self._cancel_requested
                self._process = None
                self._active_thread_id = None
                self._active_turn_id = None
                self._turn_steerable = False
                self._pending_steers = []
                self._server_read_buffer = b""
        message = messages[-1] if messages else streamed_message.strip()
        return RunResult(
            exit_code=exit_code,
            message=message,
            thread_id=active_thread_id,
            stderr="\n".join(part for part in (error_message, stderr) if part),
            cancelled=cancelled,
            timed_out=timed_out,
            token_usage=token_usage,
        )

    def steer(self, prompt: str) -> bool:
        text = prompt.strip()
        if not text:
            return False
        with self._lock:
            process = self._process
            if process is None or process.poll() is not None:
                return False
            if not self._turn_steerable or not self._active_thread_id or not self._active_turn_id:
                if len(self._pending_steers) >= 10 or sum(map(len, self._pending_steers)) + len(text) > 8_000:
                    return False
                self._pending_steers.append(text)
                return True
            return self._send_steer_locked(process, text)

    def _app_server_sandbox(self, *, approved: bool, full_access: bool) -> dict[str, object]:
        if full_access:
            return {"type": "dangerFullAccess"}
        if not approved:
            return {"type": "readOnly", "networkAccess": False}
        roots = tuple(dict.fromkeys((self.workdir, *self.additional_write_roots)))
        return {
            "type": "workspaceWrite",
            "writableRoots": [str(path) for path in roots],
            "networkAccess": self.network_access,
        }

    def _server_request(
        self,
        process: subprocess.Popen[str],
        method: str,
        params: dict[str, object],
        deadline: float,
    ) -> dict[str, object]:
        with self._lock:
            request_id = self._next_rpc_id
            self._next_rpc_id += 1
            self._write_server_message(process, {"method": method, "id": request_id, "params": params})
        while True:
            message = self._read_server_message(process, deadline)
            if message is None:
                raise RuntimeError(f"Codex app-server timed out during {method}")
            if message.get("id") == request_id:
                return message

    def _server_notify(
        self,
        process: subprocess.Popen[str],
        method: str,
        params: dict[str, object],
    ) -> None:
        with self._lock:
            self._write_server_message(process, {"method": method, "params": params})

    def _read_server_message(
        self,
        process: subprocess.Popen[str],
        deadline: float,
    ) -> dict[str, object] | None:
        if process.stdout is None:
            raise RuntimeError("Codex app-server stdout is unavailable")
        while b"\n" not in self._server_read_buffer:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            ready, _, _ = select.select([process.stdout.fileno()], [], [], remaining)
            if not ready:
                return None
            chunk = os.read(process.stdout.fileno(), 64 * 1024)
            if not chunk:
                raise RuntimeError("Codex app-server closed its protocol stream")
            self._server_read_buffer += chunk
            if len(self._server_read_buffer) > 2_000_000:
                raise RuntimeError("Codex app-server returned an oversized protocol message")
        raw_line, _, self._server_read_buffer = self._server_read_buffer.partition(b"\n")
        try:
            message = json.loads(raw_line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("Codex app-server returned invalid JSON") from exc
        if not isinstance(message, dict):
            raise RuntimeError("Codex app-server returned an invalid protocol message")
        return message

    def _flush_pending_steers(self, process: subprocess.Popen[str]) -> None:
        with self._lock:
            pending = self._pending_steers
            self._pending_steers = []
            for prompt in pending:
                self._send_steer_locked(process, prompt)

    def _send_steer_locked(self, process: subprocess.Popen[str], prompt: str) -> bool:
        if not self._active_thread_id or not self._active_turn_id:
            return False
        request_id = self._next_rpc_id
        self._next_rpc_id += 1
        try:
            self._write_server_message(
                process,
                {
                    "method": "turn/steer",
                    "id": request_id,
                    "params": {
                        "threadId": self._active_thread_id,
                        "expectedTurnId": self._active_turn_id,
                        "input": [{"type": "text", "text": prompt}],
                    },
                },
            )
        except (BrokenPipeError, OSError):
            return False
        return True

    @staticmethod
    def _write_server_message(process: subprocess.Popen[str], message: dict[str, object]) -> None:
        if process.stdin is None:
            raise RuntimeError("Codex app-server stdin is unavailable")
        process.stdin.write(json.dumps(message, separators=(",", ":")) + "\n")
        process.stdin.flush()

    @staticmethod
    def _server_error(message: dict[str, object]) -> str:
        error = message.get("error")
        if isinstance(error, dict) and isinstance(error.get("message"), str):
            return error["message"]
        return "Codex app-server request failed"

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

    def _cleanup_restricted_workspace(self) -> None:
        if not self.restricted_workdir.is_dir():
            return
        for path in self.restricted_workdir.iterdir():
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
