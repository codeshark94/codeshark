from __future__ import annotations

import getpass
import json
import os
import re
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.local.toml"
DEFAULT_CODEX_PROFILE = "codex-codeshark"
KEYCHAIN_SERVICE = "codex-codeshark.bot-token"
_BOT_TOKEN_PATTERN = re.compile(r"[0-9]+:[A-Za-z0-9_-]+")


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class Config:
    allowed_user_ids: frozenset[int]
    workdir: Path
    codex_binary: Path
    codex_profile: str = DEFAULT_CODEX_PROFILE
    poll_timeout_seconds: int = 30
    task_timeout_seconds: int = 1800
    queue_size: int = 3
    max_session_turns: int = 30
    memory_max_chars: int = 4000
    mcp_known_servers: tuple[str, ...] = ()
    mcp_allowed_tools: tuple[tuple[str, tuple[str, ...]], ...] = ()
    state_path: Path = PROJECT_ROOT / "runtime" / "state.json"


def _require_int(data: dict[str, Any], key: str, default: int) -> int:
    value = data.get(key, default)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ConfigError(f"{key} must be an integer")
    return value


def load_config(path: Path | None = None) -> Config:
    config_path = path or Path(os.environ.get("TELEGRAM_CODEX_CONFIG", DEFAULT_CONFIG_PATH))
    if not config_path.is_file():
        raise ConfigError(f"missing config: {config_path}; run setup first")

    try:
        data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"cannot read config: {exc}") from exc

    raw_ids = data.get("allowed_user_ids")
    if not isinstance(raw_ids, list) or len(raw_ids) != 1:
        raise ConfigError("allowed_user_ids must contain exactly one Telegram user ID")
    if any(not isinstance(user_id, int) or isinstance(user_id, bool) or user_id <= 0 for user_id in raw_ids):
        raise ConfigError("allowed_user_ids must contain positive integers")

    workdir = Path(str(data.get("workdir", ""))).expanduser()
    codex_binary = Path(str(data.get("codex_binary", ""))).expanduser()
    codex_profile = data.get("codex_profile", DEFAULT_CODEX_PROFILE)
    if not workdir.is_absolute() or not workdir.is_dir():
        raise ConfigError(f"workdir must be an existing absolute directory: {workdir}")
    if not codex_binary.is_absolute() or not codex_binary.is_file():
        raise ConfigError(f"codex_binary must be an existing absolute file: {codex_binary}")
    if not isinstance(codex_profile, str) or not codex_profile.strip():
        raise ConfigError("codex_profile must be a non-empty string")

    poll_timeout = _require_int(data, "poll_timeout_seconds", 30)
    task_timeout = _require_int(data, "task_timeout_seconds", 1800)
    queue_size = _require_int(data, "queue_size", 3)
    max_session_turns = _require_int(data, "max_session_turns", 30)
    memory_max_chars = _require_int(data, "memory_max_chars", 4000)
    if not 1 <= poll_timeout <= 50:
        raise ConfigError("poll_timeout_seconds must be between 1 and 50")
    if not 30 <= task_timeout <= 86400:
        raise ConfigError("task_timeout_seconds must be between 30 and 86400")
    if not 1 <= queue_size <= 20:
        raise ConfigError("queue_size must be between 1 and 20")
    if not 5 <= max_session_turns <= 500:
        raise ConfigError("max_session_turns must be between 5 and 500")
    if not 1000 <= memory_max_chars <= 20000:
        raise ConfigError("memory_max_chars must be between 1000 and 20000")

    mcp_policy = data.get("mcp_policy", {})
    if not isinstance(mcp_policy, dict):
        raise ConfigError("mcp_policy must be a table")
    raw_known_servers = mcp_policy.get("known_servers", [])
    raw_allowed_tools = mcp_policy.get("allowed_tools", {})
    if not isinstance(raw_known_servers, list) or not all(
        isinstance(name, str) and re.fullmatch(r"[A-Za-z0-9_-]+", name)
        for name in raw_known_servers
    ):
        raise ConfigError("mcp_policy.known_servers must contain safe server names")
    if len(raw_known_servers) != len(set(raw_known_servers)):
        raise ConfigError("mcp_policy.known_servers must not contain duplicates")
    if not isinstance(raw_allowed_tools, dict):
        raise ConfigError("mcp_policy.allowed_tools must be a table")
    allowed_tools: list[tuple[str, tuple[str, ...]]] = []
    for server, tools in raw_allowed_tools.items():
        if server not in raw_known_servers:
            raise ConfigError(f"MCP allowlist references unknown server: {server}")
        if not isinstance(tools, list) or not tools or not all(
            isinstance(tool, str) and re.fullmatch(r"[A-Za-z0-9_.:-]+", tool)
            for tool in tools
        ):
            raise ConfigError(f"MCP tools for {server} must be a non-empty string list")
        if len(tools) != len(set(tools)):
            raise ConfigError(f"MCP tools for {server} must not contain duplicates")
        allowed_tools.append((server, tuple(tools)))

    return Config(
        allowed_user_ids=frozenset(raw_ids),
        workdir=workdir.resolve(),
        codex_binary=codex_binary.resolve(),
        codex_profile=codex_profile.strip(),
        poll_timeout_seconds=poll_timeout,
        task_timeout_seconds=task_timeout,
        queue_size=queue_size,
        max_session_turns=max_session_turns,
        memory_max_chars=memory_max_chars,
        mcp_known_servers=tuple(raw_known_servers),
        mcp_allowed_tools=tuple(allowed_tools),
    )


def configured_mcp_servers(
    codex_profile: str,
    *,
    codex_home: Path | None = None,
) -> frozenset[str]:
    root = codex_home or Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    root = root.expanduser()
    paths = (root / "config.toml", root / f"{codex_profile}.config.toml")
    servers: set[str] = set()
    for path in paths:
        if not path.is_file():
            continue
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise ConfigError(f"cannot inspect Codex MCP config {path}: {exc}") from exc
        raw_servers = data.get("mcp_servers", {})
        if not isinstance(raw_servers, dict):
            raise ConfigError(f"mcp_servers must be a table in {path}")
        servers.update(str(name) for name in raw_servers)
    return frozenset(servers)


def validate_mcp_policy(config: Config, *, codex_home: Path | None = None) -> str:
    configured = configured_mcp_servers(config.codex_profile, codex_home=codex_home)
    known = frozenset(config.mcp_known_servers)
    unknown = sorted(configured - known)
    if unknown:
        raise ConfigError(
            "MCP servers missing from gateway policy: " + ", ".join(unknown)
        )
    stale = sorted(known - configured)
    if stale:
        raise ConfigError(
            "MCP policy references unconfigured servers: " + ", ".join(stale)
        )
    return f"{len(configured)} configured, {len(config.mcp_allowed_tools)} allowed"


def codex_profile_path(profile: str, *, codex_home: Path | None = None) -> Path:
    root = codex_home or Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    return root.expanduser() / f"{profile}.config.toml"


def write_codex_profile(profile: str, *, codex_home: Path | None = None) -> Path:
    path = codex_profile_path(profile, codex_home=codex_home)
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        'sandbox_mode = "workspace-write"\napproval_policy = "never"\n',
        encoding="utf-8",
    )
    temporary.chmod(0o600)
    os.replace(temporary, path)
    return path


def validate_codex_profile(config: Config, *, codex_home: Path | None = None) -> str:
    path = codex_profile_path(config.codex_profile, codex_home=codex_home)
    if not path.is_file():
        raise ConfigError(f"missing profile: {path}")
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"cannot read Codex profile {path}: {exc}") from exc
    if data.get("sandbox_mode") != "workspace-write":
        raise ConfigError("Codex profile sandbox_mode must be workspace-write")
    if data.get("approval_policy") != "never":
        raise ConfigError("Codex profile approval_policy must be never")
    return config.codex_profile


def keychain_account() -> str:
    return getpass.getuser()


def validate_bot_token(token: str) -> str:
    normalized = token.strip()
    if not _BOT_TOKEN_PATTERN.fullmatch(normalized):
        raise ConfigError(
            "invalid Telegram bot token format; paste only the BotFather token "
            "(numbers:letters), not a shell command"
        )
    return normalized


def load_bot_token() -> str:
    env_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if env_token:
        return validate_bot_token(env_token)

    result = subprocess.run(
        [
            "/usr/bin/security",
            "find-generic-password",
            "-a",
            keychain_account(),
            "-s",
            KEYCHAIN_SERVICE,
            "-w",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise ConfigError("Telegram token not found in Keychain; run setup first")
    return validate_bot_token(result.stdout)


def prompt_and_store_bot_token() -> str:
    token = validate_bot_token(
        getpass.getpass("BotFather token (input is hidden): ")
    )
    result = subprocess.run(
        [
            "/usr/bin/security",
            "add-generic-password",
            "-U",
            "-a",
            keychain_account(),
            "-s",
            KEYCHAIN_SERVICE,
            "-w",
        ],
        input=f"{token}\n{token}\n",
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise ConfigError("failed to store token in Keychain")
    return token


def write_local_config(
    user_id: int,
    path: Path | None = None,
    *,
    codex_home: Path | None = None,
) -> Path:
    config_path = path or DEFAULT_CONFIG_PATH
    workdir = PROJECT_ROOT / "workspace"
    codex_binary = Path("/Applications/Codex.app/Contents/Resources/codex")
    known_mcp_servers = sorted(
        configured_mcp_servers(DEFAULT_CODEX_PROFILE, codex_home=codex_home)
    )
    content = "\n".join(
        [
            f"allowed_user_ids = [{user_id}]",
            f"workdir = {json.dumps(str(workdir), ensure_ascii=False)}",
            f"codex_binary = {json.dumps(str(codex_binary), ensure_ascii=False)}",
            f'codex_profile = "{DEFAULT_CODEX_PROFILE}"',
            "poll_timeout_seconds = 30",
            "task_timeout_seconds = 1800",
            "queue_size = 3",
            "max_session_turns = 30",
            "memory_max_chars = 4000",
            "",
            "[mcp_policy]",
            "known_servers = " + json.dumps(known_mcp_servers),
            "",
            "[mcp_policy.allowed_tools]",
            "",
        ]
    )
    temporary = config_path.with_suffix(config_path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.chmod(0o600)
    os.replace(temporary, config_path)
    return config_path
