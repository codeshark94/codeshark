from __future__ import annotations

import subprocess

from .config import (
    ConfigError,
    load_bot_token,
    load_config,
    prepare_group_runtime,
    validate_codex_profile,
    validate_codex_version,
    validate_mcp_policy,
)
from .telegram_api import TelegramAPI


def run_doctor() -> int:
    failures = 0

    def check(label: str, operation) -> None:
        nonlocal failures
        try:
            detail = operation()
            suffix = f": {detail}" if detail else ""
            print(f"PASS {label}{suffix}")
        except Exception as exc:
            failures += 1
            print(f"FAIL {label}: {exc}")

    config_holder = {}

    def config_check() -> str:
        config = load_config()
        config_holder["value"] = config
        return str(config.workdir)

    check("local config", config_check)
    check("Telegram token in Keychain", lambda: "found" if load_bot_token() else "missing")

    def telegram_check() -> str:
        me = TelegramAPI(load_bot_token()).get_me()
        return "@" + str(me.get("username", "unknown"))

    check("Telegram API", telegram_check)

    def login_check() -> str:
        result = subprocess.run(
            ["/Applications/Codex.app/Contents/Resources/codex", "login", "status"],
            capture_output=True,
            text=True,
            check=False,
        )
        output = "\n".join(part for part in (result.stdout.strip(), result.stderr.strip()) if part)
        if result.returncode != 0:
            raise ConfigError(output)
        return output

    check("Codex login", login_check)

    def version_check() -> str:
        config = config_holder.get("value") or load_config()
        return validate_codex_version(config.codex_binary)

    check("Codex CLI version", version_check)

    def profile_check() -> str:
        config = config_holder.get("value") or load_config()
        return validate_codex_profile(config)

    check("Codex profile", profile_check)

    def group_runtime_check() -> str:
        config = config_holder.get("value") or load_config()
        return f"{prepare_group_runtime(config)} ({config.worker_count} workers)"

    check("isolated group runtime", group_runtime_check)

    def model_check() -> str:
        config = config_holder.get("value") or load_config()
        return (
            f"routine {config.routine_model} ({config.routine_reasoning_effort}); "
            f"primary {config.primary_model} ({config.primary_reasoning_effort}); "
            f"rework {config.rework_model} ({config.rework_reasoning_effort}); "
            f"validation {config.validator_model} ({config.validator_reasoning_effort}); "
            f"feedback {config.feedback_model} ({config.feedback_reasoning_effort}); "
            f"triage {config.triage_model} ({config.triage_reasoning_effort}); "
            f"planner {config.preflight_model} ({config.preflight_reasoning_effort}); "
            f"research {config.research_model} ({config.research_reasoning_effort}); "
            f"finalization {config.finalizer_model} ({config.finalizer_reasoning_effort}); Fast off"
        )

    check("Codex model", model_check)

    def mcp_policy_check() -> str:
        config = config_holder.get("value") or load_config()
        return validate_mcp_policy(config)

    check("MCP allowlist", mcp_policy_check)
    return 1 if failures else 0
