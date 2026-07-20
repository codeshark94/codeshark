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

from .secure_io import atomic_write_text, ensure_private_directory


_SOURCE_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_PROJECT_ROOT = (
    _SOURCE_ROOT
    if (_SOURCE_ROOT / "pyproject.toml").is_file()
    else Path.home() / ".codex-codeshark"
)
PROJECT_ROOT = Path(
    os.environ.get("CODEX_CODESHARK_HOME", _DEFAULT_PROJECT_ROOT)
).expanduser().resolve()
DEFAULT_CODEX_HOME = Path(
    os.environ.get("CODEX_HOME", Path.home() / ".codex")
).expanduser().resolve()
DEFAULT_CODEX_BINARY = Path("/Applications/Codex.app/Contents/Resources/codex")
_DEFAULT_GROUP_RUNTIME_ROOT = Path.home() / "Library" / "Application Support" / "Codex-codeshark" / "group"
GROUP_RUNTIME_ROOT = Path(
    os.environ.get("CODEX_CODESHARK_GROUP_HOME", _DEFAULT_GROUP_RUNTIME_ROOT)
).expanduser().resolve()
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.local.toml"
DEFAULT_CODEX_PROFILE = "codex-codeshark"
KEYCHAIN_SERVICE = "codex-codeshark.bot-token"
_BOT_TOKEN_PATTERN = re.compile(r"[0-9]+:[A-Za-z0-9_-]+")
_MIN_PERMISSION_PROFILE_VERSION = (0, 138, 0)
_MODEL_ID_PATTERN = re.compile(r"[A-Za-z0-9._-]{1,100}")
_MAX_REASONING_EFFORTS = frozenset({"low", "medium", "high"})


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class Config:
    allowed_user_ids: frozenset[int]
    workdir: Path
    codex_binary: Path
    codex_profile: str = DEFAULT_CODEX_PROFILE
    routine_model: str = "gpt-5.6-luna"
    routine_reasoning_effort: str = "medium"
    primary_model: str = "gpt-5.6-sol"
    primary_reasoning_effort: str = "high"
    validator_model: str = "gpt-5.6-terra"
    validator_reasoning_effort: str = "high"
    preflight_model: str = "gpt-5.6-luna"
    preflight_reasoning_effort: str = "low"
    poll_timeout_seconds: int = 30
    task_timeout_seconds: int = 1800
    queue_size: int = 20
    worker_count: int = 8
    max_session_turns: int = 30
    memory_max_chars: int = 12000
    codex_network_access: bool = False
    admin_full_access: bool = False
    attachment_max_bytes: int = 10_000_000
    read_only_roots: tuple[Path, ...] = ()
    delegated_roots: tuple[Path, ...] = ()
    mcp_known_servers: tuple[str, ...] = ()
    mcp_allowed_tools: tuple[tuple[str, tuple[str, ...]], ...] = ()
    state_path: Path = PROJECT_ROOT / "runtime" / "state.json"
    codex_home: Path = DEFAULT_CODEX_HOME
    group_workdir: Path = GROUP_RUNTIME_ROOT / "workspace"
    group_codex_home: Path = GROUP_RUNTIME_ROOT / "codex-home"
    agent_repository_root: Path = PROJECT_ROOT


def _require_int(data: dict[str, Any], key: str, default: int) -> int:
    value = data.get(key, default)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ConfigError(f"{key} must be an integer")
    return value


def _require_bool(data: dict[str, Any], key: str, default: bool) -> bool:
    value = data.get(key, default)
    if not isinstance(value, bool):
        raise ConfigError(f"{key} must be true or false")
    return value


def _require_model_setting(data: dict[str, Any], key: str, default: str) -> str:
    value = data.get(key, default)
    if not isinstance(value, str) or not _MODEL_ID_PATTERN.fullmatch(value):
        raise ConfigError(f"{key} must be a valid model identifier")
    return value


def _require_reasoning_effort(data: dict[str, Any], key: str, default: str) -> str:
    value = data.get(key, default)
    if value not in _MAX_REASONING_EFFORTS:
        allowed = ", ".join(sorted(_MAX_REASONING_EFFORTS))
        raise ConfigError(f"{key} must be one of: {allowed}")
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
    routine_model = _require_model_setting(
        data, "routine_model", data.get("codex_model", "gpt-5.6-luna")
    )
    routine_reasoning_effort = _require_reasoning_effort(
        data, "routine_reasoning_effort", "medium"
    )
    primary_model = _require_model_setting(data, "primary_model", "gpt-5.6-sol")
    primary_reasoning_effort = _require_reasoning_effort(
        data, "primary_reasoning_effort", "high"
    )
    validator_model = _require_model_setting(data, "validator_model", "gpt-5.6-terra")
    validator_reasoning_effort = _require_reasoning_effort(
        data,
        "validator_reasoning_effort",
        data.get("subagent_reasoning_effort", "high"),
    )
    preflight_model = _require_model_setting(data, "preflight_model", "gpt-5.6-luna")
    preflight_reasoning_effort = _require_reasoning_effort(
        data, "preflight_reasoning_effort", "low"
    )
    if not workdir.is_absolute() or not workdir.is_dir():
        raise ConfigError(f"workdir must be an existing absolute directory: {workdir}")
    if not codex_binary.is_absolute() or not codex_binary.is_file():
        raise ConfigError(f"codex_binary must be an existing absolute file: {codex_binary}")
    if not isinstance(codex_profile, str) or not codex_profile.strip():
        raise ConfigError("codex_profile must be a non-empty string")
    agent_repository_root = PROJECT_ROOT.resolve()
    if not agent_repository_root.is_dir():
        raise ConfigError(
            "Codeshark source repository must be an existing directory: "
            f"{agent_repository_root}"
        )

    poll_timeout = _require_int(data, "poll_timeout_seconds", 30)
    task_timeout = _require_int(data, "task_timeout_seconds", 1800)
    queue_size = _require_int(data, "queue_size", 20)
    worker_count = _require_int(data, "worker_count", 8)
    max_session_turns = _require_int(data, "max_session_turns", 30)
    memory_max_chars = _require_int(data, "memory_max_chars", 12000)
    codex_network_access = _require_bool(data, "codex_network_access", False)
    admin_full_access = _require_bool(data, "admin_full_access", False)
    attachment_max_bytes = _require_int(data, "attachment_max_bytes", 10_000_000)
    if not 1 <= poll_timeout <= 50:
        raise ConfigError("poll_timeout_seconds must be between 1 and 50")
    if not 30 <= task_timeout <= 86400:
        raise ConfigError("task_timeout_seconds must be between 30 and 86400")
    if queue_size < 1:
        raise ConfigError("queue_size must be positive")
    if worker_count < 1:
        raise ConfigError("worker_count must be positive")
    if not 5 <= max_session_turns <= 500:
        raise ConfigError("max_session_turns must be between 5 and 500")
    if not 1000 <= memory_max_chars <= 20000:
        raise ConfigError("memory_max_chars must be between 1000 and 20000")
    if not 1_000_000 <= attachment_max_bytes <= 50_000_000:
        raise ConfigError("attachment_max_bytes must be between 1 MB and 50 MB")

    raw_read_only_roots = data.get("read_only_roots", [])
    if not isinstance(raw_read_only_roots, list) or len(raw_read_only_roots) > 20:
        raise ConfigError("read_only_roots must be a list of at most 20 directories")
    read_only_roots: list[Path] = []
    for raw_root in raw_read_only_roots:
        if not isinstance(raw_root, str):
            raise ConfigError("read_only_roots must contain directory paths")
        root = Path(raw_root).expanduser()
        if not root.is_absolute() or not root.is_dir():
            raise ConfigError(f"read_only_roots must contain existing absolute directories: {root}")
        resolved = root.resolve()
        if resolved not in read_only_roots:
            read_only_roots.append(resolved)

    raw_delegated_roots = data.get("delegated_roots", [])
    if not isinstance(raw_delegated_roots, list) or len(raw_delegated_roots) > 20:
        raise ConfigError("delegated_roots must be a list of at most 20 directories")
    delegated_roots: list[Path] = []
    for raw_root in raw_delegated_roots:
        if not isinstance(raw_root, str):
            raise ConfigError("delegated_roots must contain directory paths")
        root = Path(raw_root).expanduser()
        if not root.is_absolute() or not root.is_dir():
            raise ConfigError(f"delegated_roots must contain existing absolute directories: {root}")
        resolved = root.resolve()
        if resolved not in delegated_roots:
            delegated_roots.append(resolved)
    overlap = {
        (read_root, delegated_root)
        for read_root in read_only_roots
        for delegated_root in delegated_roots
        if (
            read_root == delegated_root
            or read_root in delegated_root.parents
            or delegated_root in read_root.parents
        )
    }
    if overlap:
        raise ConfigError(
            "read-only and delegated project roots cannot overlap: "
            + ", ".join(
                f"{read_root} <> {delegated_root}"
                for read_root, delegated_root in sorted(overlap)
            )
        )

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
        routine_model=routine_model,
        routine_reasoning_effort=routine_reasoning_effort,
        primary_model=primary_model,
        primary_reasoning_effort=primary_reasoning_effort,
        validator_model=validator_model,
        validator_reasoning_effort=validator_reasoning_effort,
        preflight_model=preflight_model,
        preflight_reasoning_effort=preflight_reasoning_effort,
        poll_timeout_seconds=poll_timeout,
        task_timeout_seconds=task_timeout,
        queue_size=queue_size,
        worker_count=worker_count,
        max_session_turns=max_session_turns,
        memory_max_chars=memory_max_chars,
        codex_network_access=codex_network_access,
        admin_full_access=admin_full_access,
        attachment_max_bytes=attachment_max_bytes,
        read_only_roots=tuple(read_only_roots),
        delegated_roots=tuple(delegated_roots),
        mcp_known_servers=tuple(raw_known_servers),
        mcp_allowed_tools=tuple(allowed_tools),
        agent_repository_root=agent_repository_root,
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


def configured_codex_runtime(
    codex_profile: str,
    *,
    codex_home: Path | None = None,
) -> tuple[str | None, str | None]:
    root = (codex_home or DEFAULT_CODEX_HOME).expanduser()
    model: str | None = None
    reasoning_effort: str | None = None
    for path in (root / "config.toml", root / f"{codex_profile}.config.toml"):
        if not path.is_file():
            continue
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise ConfigError(f"cannot inspect Codex runtime config {path}: {exc}") from exc
        if isinstance(data.get("model"), str) and data["model"].strip():
            model = data["model"].strip()
        if (
            isinstance(data.get("model_reasoning_effort"), str)
            and data["model_reasoning_effort"].strip()
        ):
            reasoning_effort = data["model_reasoning_effort"].strip()
    return model, reasoning_effort


def _prepare_group_runtime_slot(
    workdir: Path,
    isolated_home: Path,
    auth_source: Path,
) -> None:
    workdir.mkdir(parents=True, exist_ok=True)
    isolated_home.mkdir(parents=True, exist_ok=True)
    workdir.chmod(0o700)
    isolated_home.chmod(0o700)

    auth_link = isolated_home / "auth.json"
    if auth_link.exists() or auth_link.is_symlink():
        if not auth_link.is_symlink() or auth_link.resolve() != auth_source:
            raise ConfigError(
                "group Codex home contains an unexpected auth.json; remove it and rerun doctor"
            )
    else:
        auth_link.symlink_to(auth_source)


def group_worker_runtime(config: Config, worker_index: int) -> tuple[Path, Path]:
    if not 0 <= worker_index < config.worker_count:
        raise ValueError("worker index is outside the configured worker count")
    workdir = config.group_workdir.expanduser().resolve() / f"worker-{worker_index + 1}"
    isolated_home = config.group_codex_home.expanduser().resolve() / f"worker-{worker_index + 1}"
    return workdir, isolated_home


def prepare_group_runtime(config: Config) -> str:
    workdir = config.group_workdir.expanduser().resolve()
    isolated_home = config.group_codex_home.expanduser().resolve()
    if (
        workdir == isolated_home
        or workdir in isolated_home.parents
        or isolated_home in workdir.parents
    ):
        raise ConfigError("group_workdir and group_codex_home must be separate directories")

    auth_source = (config.codex_home / "auth.json").expanduser().resolve()
    if not auth_source.is_file():
        raise ConfigError(f"Codex authentication file is missing: {auth_source}")
    _prepare_group_runtime_slot(workdir, isolated_home, auth_source)
    for worker_index in range(config.worker_count):
        slot_workdir, slot_home = group_worker_runtime(config, worker_index)
        _prepare_group_runtime_slot(slot_workdir, slot_home, auth_source)
    return str(workdir)


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
    ensure_private_directory(path.parent)
    if path.exists():
        original = path.read_text(encoding="utf-8")
        updated = _standardize_codex_profile(original)
        if updated != original:
            atomic_write_text(path, updated)
        return path
    atomic_write_text(
        path,
        'sandbox_mode = "workspace-write"\napproval_policy = "never"\n'
        'service_tier = "standard"\n\n'
        '[features]\nfast_mode = false\n\n'
        '[sandbox_workspace_write]\nnetwork_access = false\n',
    )
    return path


def _standardize_codex_profile(content: str) -> str:
    """Apply Codeshark's managed execution-tier settings without dropping profile extras."""
    content = re.sub(r"(?m)^service_tier\s*=.*(?:\n|$)", "", content)
    first_table = re.search(r"(?m)^\[", content)
    insertion = first_table.start() if first_table else len(content)
    content = (
        content[:insertion]
        + 'service_tier = "standard"\n'
        + content[insertion:]
    )
    features = re.search(r"(?m)^\[features\]\s*$", content)
    if features is None:
        return content.rstrip() + "\n\n[features]\nfast_mode = false\n"
    section_end = re.search(r"(?m)^\[(?!features\])", content[features.end() :])
    end = features.end() + section_end.start() if section_end else len(content)
    section = content[features.end() : end]
    if re.search(r"(?m)^fast_mode\s*=.*$", section):
        section = re.sub(r"(?m)^fast_mode\s*=.*$", "fast_mode = false", section)
    else:
        section = "\nfast_mode = false" + section
    return content[: features.end()] + section + content[end:]


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
    if data.get("service_tier") != "standard":
        raise ConfigError("Codex profile service_tier must be standard")
    features = data.get("features")
    if not isinstance(features, dict) or features.get("fast_mode") is not False:
        raise ConfigError("Codex profile must disable Fast mode")
    return config.codex_profile


def validate_codex_version(binary: Path) -> str:
    result = subprocess.run(
        [str(binary), "--version"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    output = "\n".join(part for part in (result.stdout.strip(), result.stderr.strip()) if part)
    match = re.search(r"\b(\d+)\.(\d+)\.(\d+)\b", output)
    if result.returncode != 0 or match is None:
        raise ConfigError(f"could not determine Codex CLI version: {output or 'no output'}")
    version = tuple(int(part) for part in match.groups())
    if version < _MIN_PERMISSION_PROFILE_VERSION:
        required = ".".join(str(part) for part in _MIN_PERMISSION_PROFILE_VERSION)
        raise ConfigError(
            f"Codex CLI {match.group(0)} is too old; group isolation requires {required} or newer"
        )
    return match.group(0)


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
    project_root: Path | None = None,
) -> Path:
    root = project_root or PROJECT_ROOT
    config_path = path or root / "config.local.toml"
    workdir = root / "workspace"
    workdir.mkdir(parents=True, exist_ok=True)
    workdir.chmod(0o700)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    codex_binary = DEFAULT_CODEX_BINARY
    known_mcp_servers = sorted(
        configured_mcp_servers(DEFAULT_CODEX_PROFILE, codex_home=codex_home)
    )
    content = "\n".join(
        [
            f"allowed_user_ids = [{user_id}]",
            f"workdir = {json.dumps(str(workdir), ensure_ascii=False)}",
            f"codex_binary = {json.dumps(str(codex_binary), ensure_ascii=False)}",
            f'codex_profile = "{DEFAULT_CODEX_PROFILE}"',
            'routine_model = "gpt-5.6-luna"',
            'routine_reasoning_effort = "medium"',
            'primary_model = "gpt-5.6-sol"',
            'primary_reasoning_effort = "high"',
            'validator_model = "gpt-5.6-terra"',
            'validator_reasoning_effort = "high"',
            'preflight_model = "gpt-5.6-luna"',
            'preflight_reasoning_effort = "low"',
            "poll_timeout_seconds = 30",
            "task_timeout_seconds = 1800",
            "queue_size = 20",
            "worker_count = 8",
            "max_session_turns = 30",
            "memory_max_chars = 12000",
            "codex_network_access = false",
            "admin_full_access = false",
            "attachment_max_bytes = 10000000",
            "read_only_roots = []",
            "delegated_roots = []",
            "",
            "[mcp_policy]",
            "known_servers = " + json.dumps(known_mcp_servers),
            "",
            "[mcp_policy.allowed_tools]",
            "",
        ]
    )
    atomic_write_text(config_path, content, private_parent=False)
    return config_path
