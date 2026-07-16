from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


class TelegramError(RuntimeError):
    pass


class TelegramAPI:
    def __init__(self, token: str) -> None:
        self._base_url = f"https://api.telegram.org/bot{token}"

    def call(self, method: str, payload: dict[str, Any] | None = None, *, timeout: int = 40) -> Any:
        encoded = urllib.parse.urlencode(payload or {}).encode("utf-8")
        request = urllib.request.Request(
            f"{self._base_url}/{method}",
            data=encoded,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
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
            {"command": "help", "description": "사용법 보기"},
            {"command": "status", "description": "작업 및 세션 상태"},
            {"command": "new", "description": "현재 세션 삭제 후 새로 시작"},
            {"command": "remember", "description": "장기 메모리 저장"},
            {"command": "memories", "description": "장기 메모리 목록"},
            {"command": "forget", "description": "장기 메모리 삭제"},
            {"command": "learn", "description": "메모리 또는 스킬 후보 생성"},
            {"command": "learning", "description": "대기 중 학습 후보"},
            {"command": "approve", "description": "학습 또는 위험 작업 승인"},
            {"command": "reject", "description": "학습 또는 위험 작업 거절"},
            {"command": "skills", "description": "승인된 스킬 목록"},
            {"command": "forget_skill", "description": "승인된 스킬 삭제"},
            {"command": "tasks", "description": "최근 영속 작업 상태"},
            {"command": "remind", "description": "일회성 예약 작업"},
            {"command": "cron", "description": "cron 반복 작업"},
            {"command": "heartbeat", "description": "주기적 점검 작업"},
            {"command": "jobs", "description": "예약 작업 목록"},
            {"command": "pause", "description": "예약 작업 일시정지"},
            {"command": "resume_job", "description": "예약 작업 재개"},
            {"command": "delete_job", "description": "예약 작업 삭제"},
            {"command": "mcp", "description": "MCP 도구 allowlist"},
            {"command": "good", "description": "직전 작업을 좋음으로 평가"},
            {"command": "bad", "description": "직전 작업을 나쁨으로 평가"},
            {"command": "cancel", "description": "현재 작업 취소"},
        ]
        self.call("setMyCommands", {"commands": json.dumps(commands, ensure_ascii=False)})
