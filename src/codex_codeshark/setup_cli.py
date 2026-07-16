from __future__ import annotations

import secrets
import subprocess
import time

from .config import (
    DEFAULT_CODEX_PROFILE,
    load_bot_token,
    prompt_and_store_bot_token,
    write_codex_profile,
    write_local_config,
)
from .telegram_api import TelegramAPI


def interactive_setup() -> int:
    login = subprocess.run(
        ["/Applications/Codex.app/Contents/Resources/codex", "login", "status"],
        capture_output=True,
        text=True,
        check=False,
    )
    login_output = "\n".join(part for part in (login.stdout.strip(), login.stderr.strip()) if part)
    if login.returncode != 0 or "Logged in" not in login_output:
        print("Codex CLI가 로그인되어 있지 않습니다. 먼저 `codex login`을 실행하세요.")
        return 1

    print("이어지는 macOS Keychain 프롬프트에 BotFather 토큰을 입력하세요.")
    prompt_and_store_bot_token()
    token = load_bot_token()

    api = TelegramAPI(token)
    me = api.get_me()
    api.delete_webhook(drop_pending_updates=True)
    pair_code = secrets.token_hex(4).upper()
    username = me.get("username", "unknown_bot")
    print(f"Telegram에서 @{username}에게 다음 메시지를 3분 안에 보내세요:")
    print(f"/pair {pair_code}")

    deadline = time.monotonic() + 180
    offset: int | None = None
    paired_user_id: int | None = None
    while time.monotonic() < deadline and paired_user_id is None:
        updates = api.get_updates(offset=offset, timeout=20)
        for update in updates:
            update_id = update.get("update_id")
            if isinstance(update_id, int):
                offset = update_id + 1
            message = update.get("message")
            if not isinstance(message, dict):
                continue
            chat = message.get("chat")
            sender = message.get("from")
            if not isinstance(chat, dict) or not isinstance(sender, dict):
                continue
            if chat.get("type") != "private":
                continue
            if message.get("text") == f"/pair {pair_code}" and isinstance(sender.get("id"), int):
                paired_user_id = sender["id"]
                break

    if paired_user_id is None:
        print("페어링 시간이 만료됐습니다. 다시 setup을 실행하세요.")
        return 1

    config_path = write_local_config(paired_user_id)
    profile_path = write_codex_profile(DEFAULT_CODEX_PROFILE)
    api.set_commands()
    api.delete_webhook(drop_pending_updates=True)
    api.send_message(paired_user_id, "페어링 완료. 이제 로컬에서 doctor를 실행하세요.")
    print(f"페어링 완료: Telegram user {paired_user_id}")
    print(f"설정 파일: {config_path}")
    print(f"Codex profile: {profile_path}")
    return 0
