from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from .config import ConfigError, validate_bot_token


class TelegramError(RuntimeError):
    pass


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
        self._ssl_context = build_ssl_context()

    def call(self, method: str, payload: dict[str, Any] | None = None, *, timeout: int = 40) -> Any:
        encoded = urllib.parse.urlencode(payload or {}).encode("utf-8")
        request = urllib.request.Request(
            f"{self._base_url}/{method}",
            data=encoded,
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                request,
                timeout=timeout,
                context=self._ssl_context,
            ) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise TelegramError(f"Telegram {method} failed with HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise TelegramError(f"Telegram {method} connection failed: {exc.reason}") from exc
        except TimeoutError as exc:
            raise TelegramError(f"Telegram {method} timed out") from exc
        except json.JSONDecodeError as exc:
            raise TelegramError(f"Telegram {method} returned invalid JSON") from exc

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
        )

    def send_typing(self, chat_id: int) -> None:
        self.call("sendChatAction", {"chat_id": chat_id, "action": "typing"})

    def set_commands(self) -> None:
        commands = [
            {"command": "help", "description": "Show command help"},
            {"command": "status", "description": "Show task and session status"},
            {"command": "new", "description": "Delete the current session"},
            {"command": "remember", "description": "Store a long-term memory"},
            {"command": "memories", "description": "List long-term memories"},
            {"command": "forget", "description": "Delete a long-term memory"},
            {"command": "learn", "description": "Propose a memory or skill"},
            {"command": "learning", "description": "List learning proposals"},
            {"command": "approve", "description": "Approve learning or risky work"},
            {"command": "reject", "description": "Reject learning or risky work"},
            {"command": "skills", "description": "List approved skills"},
            {"command": "forget_skill", "description": "Delete an approved skill"},
            {"command": "tasks", "description": "List recent persistent tasks"},
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
