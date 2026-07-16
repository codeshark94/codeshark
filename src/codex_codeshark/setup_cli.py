from __future__ import annotations

import secrets
import subprocess
import time

from .config import (
    DEFAULT_CODEX_PROFILE,
    load_config,
    prepare_group_runtime,
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
        print("Codex CLI is not logged in. Run `codex login` first.")
        return 1

    print("Paste only the BotFather token (numbers:characters), not a shell command.")
    token = prompt_and_store_bot_token()

    api = TelegramAPI(token)
    me = api.get_me()
    api.delete_webhook(drop_pending_updates=True)
    pair_code = secrets.token_hex(4).upper()
    username = me.get("username", "unknown_bot")
    print(f"Send the following message to @{username} on Telegram within 3 minutes:")
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
        print("Pairing timed out. Run setup again.")
        return 1

    config_path = write_local_config(paired_user_id)
    profile_path = write_codex_profile(DEFAULT_CODEX_PROFILE)
    prepare_group_runtime(load_config(config_path))
    api.set_commands()
    api.delete_webhook(drop_pending_updates=True)
    api.send_message(paired_user_id, "Pairing complete. Run the local doctor command next.")
    print(f"Pairing complete: Telegram user {paired_user_id}")
    print(f"Config file: {config_path}")
    print(f"Codex profile: {profile_path}")
    return 0
