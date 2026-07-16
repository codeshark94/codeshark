from __future__ import annotations

import json
import os
import ssl
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from .config import ConfigError, validate_bot_token


class TelegramError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        retry_after: int | None = None,
        ambiguous_delivery: bool = False,
    ) -> None:
        super().__init__(message)
        self.retry_after = retry_after
        self.ambiguous_delivery = ambiguous_delivery


def build_ssl_context() -> ssl.SSLContext:
    default_paths = ssl.get_default_verify_paths()
    if default_paths.cafile or default_paths.capath:
        return ssl.create_default_context()
    for candidate in (Path("/etc/ssl/cert.pem"), Path("/private/etc/ssl/cert.pem")):
        if candidate.is_file():
            return ssl.create_default_context(cafile=str(candidate))
    return ssl.create_default_context()


class TelegramAPI:
    def __init__(self, token: str) -> None:
        try:
            validated = validate_bot_token(token)
        except ConfigError as exc:
            raise TelegramError("Telegram bot token format is invalid") from exc
        self._base_url = f"https://api.telegram.org/bot{validated}"
        self._file_base_url = f"https://api.telegram.org/file/bot{validated}"
        self._ssl_context = build_ssl_context()

    @staticmethod
    def _http_error_detail(exc: urllib.error.HTTPError) -> tuple[str, int | None]:
        description = ""
        retry_after = None
        try:
            body = json.loads(exc.read().decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            body = None
        if isinstance(body, dict):
            if isinstance(body.get("description"), str):
                description = body["description"]
            parameters = body.get("parameters")
            if isinstance(parameters, dict) and isinstance(parameters.get("retry_after"), int):
                retry_after = max(1, min(parameters["retry_after"], 30))
        return description, retry_after

    def call(
        self,
        method: str,
        payload: dict[str, Any] | None = None,
        *,
        timeout: int = 40,
        retry_network: bool = True,
        max_attempts: int = 3,
    ) -> Any:
        encoded = urllib.parse.urlencode(payload or {}).encode("utf-8")
        request = urllib.request.Request(
            f"{self._base_url}/{method}",
            data=encoded,
            method="POST",
        )
        attempts = max(1, min(max_attempts, 3))
        for attempt in range(attempts):
            try:
                with urllib.request.urlopen(
                    request,
                    timeout=timeout,
                    context=self._ssl_context,
                ) as response:
                    body = json.loads(response.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as exc:
                description, retry_after = self._http_error_detail(exc)
                if exc.code == 429 and attempt + 1 < attempts:
                    time.sleep(retry_after or min(2 ** attempt, 4))
                    continue
                if retry_network and 500 <= exc.code < 600 and attempt + 1 < attempts:
                    time.sleep(min(2 ** attempt, 4))
                    continue
                detail = f": {description}" if description else ""
                raise TelegramError(
                    f"Telegram {method} failed with HTTP {exc.code}{detail}",
                    retry_after=retry_after,
                ) from exc
            except urllib.error.URLError as exc:
                if retry_network and attempt + 1 < attempts:
                    time.sleep(min(2 ** attempt, 4))
                    continue
                raise TelegramError(
                    f"Telegram {method} connection failed: {exc.reason}",
                    ambiguous_delivery=not retry_network,
                ) from exc
            except TimeoutError as exc:
                if retry_network and attempt + 1 < attempts:
                    time.sleep(min(2 ** attempt, 4))
                    continue
                raise TelegramError(
                    f"Telegram {method} timed out",
                    ambiguous_delivery=not retry_network,
                ) from exc
            except json.JSONDecodeError as exc:
                raise TelegramError(f"Telegram {method} returned invalid JSON") from exc

        if not isinstance(body, dict):
            raise TelegramError(f"Telegram {method} returned invalid JSON data")
        if not body.get("ok"):
            description = body.get("description", "unknown Telegram error")
            raise TelegramError(f"Telegram {method} failed: {description}")
        return body.get("result")

    def get_me(self) -> dict[str, Any]:
        return self.call("getMe")

    def delete_webhook(self, *, drop_pending_updates: bool = False) -> bool:
        return bool(
            self.call(
                "deleteWebhook",
                {"drop_pending_updates": json.dumps(drop_pending_updates)},
            )
        )

    def get_updates(self, *, offset: int | None, timeout: int) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {
            "timeout": timeout,
            "allowed_updates": json.dumps(["message"]),
        }
        if offset is not None:
            payload["offset"] = offset
        result = self.call("getUpdates", payload, timeout=timeout + 10)
        return result if isinstance(result, list) else []

    def send_message(self, chat_id: int, text: str) -> None:
        self.call(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": text,
                "disable_web_page_preview": "true",
            },
            retry_network=False,
        )

    def get_file(self, file_id: str) -> dict[str, Any]:
        result = self.call("getFile", {"file_id": file_id})
        if not isinstance(result, dict):
            raise TelegramError("Telegram getFile returned an invalid result")
        return result

    def download_file(self, file_id: str, destination: Path, *, max_bytes: int) -> int:
        metadata = self.get_file(file_id)
        file_path = metadata.get("file_path")
        file_size = metadata.get("file_size")
        if not isinstance(file_path, str) or not file_path:
            raise TelegramError("Telegram did not return a download path")
        path_parts = file_path.split("/")
        if (
            file_path.startswith("/")
            or any(part in {"", ".", ".."} for part in path_parts)
            or any(ord(character) < 32 for character in file_path)
        ):
            raise TelegramError("Telegram returned an unsafe download path")
        if isinstance(file_size, int) and file_size > max_bytes:
            raise TelegramError(f"The attachment exceeds the {max_bytes}-byte limit")

        request = urllib.request.Request(f"{self._file_base_url}/{file_path}", method="GET")
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with urllib.request.urlopen(
                request,
                timeout=60,
                context=self._ssl_context,
            ) as response:
                content_length = response.headers.get("Content-Length")
                if content_length and int(content_length) > max_bytes:
                    raise TelegramError(f"The attachment exceeds the {max_bytes}-byte limit")
                content = response.read(max_bytes + 1)
            if len(content) > max_bytes:
                raise TelegramError(f"The attachment exceeds the {max_bytes}-byte limit")
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{destination.name}.",
                suffix=".tmp",
                dir=destination.parent,
            )
            temporary_path = Path(temporary_name)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
            temporary_path.chmod(0o600)
            os.replace(temporary_path, destination)
            return len(content)
        except TelegramError:
            raise
        except urllib.error.HTTPError as exc:
            raise TelegramError(
                f"Telegram file download failed with HTTP {exc.code}"
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            raise TelegramError("Telegram file download failed") from exc
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()

    def set_commands(self) -> None:
        commands = [
            {"command": "help", "description": "Show command help"},
            {"command": "status", "description": "Show task and session status"},
            {"command": "new", "description": "Delete the current session"},
            {"command": "remember", "description": "Store a long-term memory"},
            {"command": "memories", "description": "List long-term memories"},
            {"command": "forget", "description": "Delete a long-term memory"},
            {"command": "recall", "description": "Search approved memories and skills"},
            {"command": "review_memories", "description": "Review stale or low-quality memories"},
            {"command": "learn", "description": "Propose a memory or skill"},
            {"command": "learning", "description": "List learning proposals"},
            {"command": "approve", "description": "Approve learning or risky work"},
            {"command": "reject", "description": "Reject learning or risky work"},
            {"command": "skills", "description": "List approved skills"},
            {"command": "forget_skill", "description": "Delete an approved skill"},
            {"command": "tasks", "description": "List recent persistent tasks"},
            {"command": "deliveries", "description": "List failed Telegram replies"},
            {"command": "retry_delivery", "description": "Retry a failed Telegram reply"},
            {"command": "remind", "description": "Create a one-time job"},
            {"command": "cron", "description": "Create a recurring cron job"},
            {"command": "heartbeat", "description": "Create a periodic check"},
            {"command": "jobs", "description": "List scheduled jobs"},
            {"command": "pause", "description": "Pause a scheduled job"},
            {"command": "resume_job", "description": "Resume a scheduled job"},
            {"command": "delete_job", "description": "Delete a scheduled job"},
            {"command": "mcp", "description": "Show the MCP tool allowlist"},
            {"command": "good", "description": "Rate the last task positively"},
            {"command": "bad", "description": "Rate the last task negatively"},
            {"command": "cancel", "description": "Cancel the current task"},
        ]
        self.call("setMyCommands", {"commands": json.dumps(commands, ensure_ascii=False)})
