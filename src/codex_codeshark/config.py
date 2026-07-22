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
_REASONING_EFFORTS = frozenset({"low", "medium", "high", "xhigh", "max", "ultra"})
ORCHESTRATION_TIERS = (
    "quick",
    "routine",
    "standard",
    "deep",
    "high_assurance",
)


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class OrchestrationProfile:
    uses_preflight: bool
    uses_research: bool
    uses_validator: bool
    feedback_iterations: int
    uses_finalizer: bool
    uses_adversarial_review: bool = False


@dataclass(frozen=True)
class Config:
    allowed_user_ids: frozenset[int]
    workdir: Path
    codex_binary: Path
    codex_profile: str = DEFAULT_CODEX_PROFILE
    quick_model: str = "gpt-5.4-mini"
    quick_reasoning_effort: str = "low"
    routine_model: str = "gpt-5.6-luna"
    routine_reasoning_effort: str = "low"
    primary_model: str = "gpt-5.6-sol"
    primary_reasoning_effort: str = "high"
    rework_model: str = "gpt-5.6-sol"
    rework_reasoning_effort: str = "high"
    validator_model: str = "gpt-5.6-terra"
    validator_reasoning_effort: str = "high"
    feedback_model: str = "gpt-5.6-terra"
    feedback_reasoning_effort: str = "high"
    router_model: str = "gpt-5.4-mini"
    router_reasoning_effort: str = "low"
    triage_model: str = "gpt-5.4-mini"
    triage_reasoning_effort: str = "low"
    preflight_model: str = "gpt-5.6-luna"
    preflight_reasoning_effort: str = "low"
    research_model: str = "gpt-5.6-luna"
    research_reasoning_effort: str = "medium"
    finalizer_model: str = "gpt-5.6-sol"
    finalizer_reasoning_effort: str = "medium"
    quick_uses_preflight: bool = False
    quick_uses_research: bool = False
    quick_uses_validator: bool = False
    quick_feedback_iterations: int = 0
    quick_uses_finalizer: bool = False
    quick_uses_adversarial_review: bool = False
    routine_uses_preflight: bool = False
    routine_uses_research: bool = False
    routine_uses_validator: bool = False
    routine_feedback_iterations: int = 0
    routine_uses_finalizer: bool = False
    routine_uses_adversarial_review: bool = False
    standard_uses_preflight: bool = False
    standard_uses_research: bool = False
    standard_uses_validator: bool = True
    standard_feedback_iterations: int = 0
    standard_uses_finalizer: bool = True
    standard_uses_adversarial_review: bool = False
    deep_uses_preflight: bool = True
    deep_uses_research: bool = False
    deep_uses_validator: bool = True
    deep_feedback_iterations: int = 1
    deep_uses_finalizer: bool = True
    deep_uses_adversarial_review: bool = True
    high_assurance_uses_preflight: bool = True
    high_assurance_uses_research: bool = True
    high_assurance_uses_validator: bool = True
    high_assurance_feedback_iterations: int = 2
    high_assurance_uses_finalizer: bool = True
    high_assurance_uses_adversarial_review: bool = True
    poll_timeout_seconds: int = 30
    task_timeout_seconds: int = 0
    queue_size: int = 20
    worker_count: int = 8
    max_session_turns: int = 120
    temporary_context_retention_days: int = 14
    memory_max_chars: int = 12000
    codex_network_access: bool = False
    admin_full_access: bool = False
    admin_auto_approve_actions: bool = False
    admin_mcp_enabled: bool = True
    admin_delegated_write_access: bool = True
    group_auto_enable_on_admin_address: bool = False
    group_member_requests_enabled: bool = True
    group_auto_register_members: bool = False
    group_require_registered_members: bool = False
    group_respond_to_mentions: bool = True
    group_respond_to_bot_replies: bool = True
    group_respond_to_addressed_threads: bool = True
    group_network_access: bool = True
    group_workspace_write: bool = True
    group_file_delivery_enabled: bool = True
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
    if value not in _REASONING_EFFORTS:
        allowed = ", ".join(sorted(_REASONING_EFFORTS))
        raise ConfigError(f"{key} must be one of: {allowed}")
    return value


_DEFAULT_ORCHESTRATION_PROFILES = {
    "quick": OrchestrationProfile(False, False, False, 0, False),
    "routine": OrchestrationProfile(False, False, False, 0, False),
    "standard": OrchestrationProfile(False, False, True, 0, True),
    "deep": OrchestrationProfile(True, False, True, 1, True, True),
    "high_assurance": OrchestrationProfile(True, True, True, 2, True, True),
}


def _load_orchestration_profile(
    data: dict[str, Any],
    tier: str,
    *,
    legacy_tier: str | None = None,
) -> OrchestrationProfile:
    default = _DEFAULT_ORCHESTRATION_PROFILES[tier]

    def value(name: str, fallback: bool | int) -> bool | int:
        key = f"{tier}_{name}"
        if key in data:
            return data[key]
        if legacy_tier is not None:
            legacy_key = f"{legacy_tier}_{name}"
            if legacy_key in data:
                return data[legacy_key]
        return fallback

    preflight = value("uses_preflight", default.uses_preflight)
    research = value("uses_research", default.uses_research)
    validator = value("uses_validator", default.uses_validator)
    feedback = value("feedback_iterations", default.feedback_iterations)
    finalizer = value("uses_finalizer", default.uses_finalizer)
    adversarial = value("uses_adversarial_review", default.uses_adversarial_review)
    for name, setting in (
        ("uses_preflight", preflight),
        ("uses_research", research),
        ("uses_validator", validator),
        ("uses_finalizer", finalizer),
        ("uses_adversarial_review", adversarial),
    ):
        if not isinstance(setting, bool):
            raise ConfigError(f"{tier}_{name} must be true or false")
    if not isinstance(feedback, int) or isinstance(feedback, bool):
        raise ConfigError(f"{tier}_feedback_iterations must be an integer")
    return OrchestrationProfile(
        preflight,
        research,
        validator,
        feedback,
        finalizer,
        adversarial,
    )


def orchestration_profiles(config: Config) -> dict[str, OrchestrationProfile]:
    return {
        "quick": OrchestrationProfile(
            config.quick_uses_preflight,
            config.quick_uses_research,
            config.quick_uses_validator,
            config.quick_feedback_iterations,
            config.quick_uses_finalizer,
            config.quick_uses_adversarial_review,
        ),
        "routine": OrchestrationProfile(
            config.routine_uses_preflight,
            config.routine_uses_research,
            config.routine_uses_validator,
            config.routine_feedback_iterations,
            config.routine_uses_finalizer,
            config.routine_uses_adversarial_review,
        ),
        "standard": OrchestrationProfile(
            config.standard_uses_preflight,
            config.standard_uses_research,
            config.standard_uses_validator,
            config.standard_feedback_iterations,
            config.standard_uses_finalizer,
            config.standard_uses_adversarial_review,
        ),
        "deep": OrchestrationProfile(
            config.deep_uses_preflight,
            config.deep_uses_research,
            config.deep_uses_validator,
            config.deep_feedback_iterations,
            config.deep_uses_finalizer,
            config.deep_uses_adversarial_review,
        ),
        "high_assurance": OrchestrationProfile(
            config.high_assurance_uses_preflight,
            config.high_assurance_uses_research,
            config.high_assurance_uses_validator,
            config.high_assurance_feedback_iterations,
            config.high_assurance_uses_finalizer,
            config.high_assurance_uses_adversarial_review,
        ),
    }


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
    quick_model = _require_model_setting(data, "quick_model", "gpt-5.4-mini")
    quick_reasoning_effort = _require_reasoning_effort(
        data, "quick_reasoning_effort", "low"
    )
    routine_model = _require_model_setting(
        data, "routine_model", data.get("codex_model", "gpt-5.6-luna")
    )
    routine_reasoning_effort = _require_reasoning_effort(
        data, "routine_reasoning_effort", "low"
    )
    primary_model = _require_model_setting(data, "primary_model", "gpt-5.6-sol")
    primary_reasoning_effort = _require_reasoning_effort(
        data, "primary_reasoning_effort", "high"
    )
    rework_model = _require_model_setting(data, "rework_model", primary_model)
    rework_reasoning_effort = _require_reasoning_effort(
        data, "rework_reasoning_effort", primary_reasoning_effort
    )
    validator_model = _require_model_setting(data, "validator_model", "gpt-5.6-terra")
    validator_reasoning_effort = _require_reasoning_effort(
        data,
        "validator_reasoning_effort",
        data.get("subagent_reasoning_effort", "high"),
    )
    feedback_model = _require_model_setting(data, "feedback_model", validator_model)
    feedback_reasoning_effort = _require_reasoning_effort(
        data, "feedback_reasoning_effort", validator_reasoning_effort
    )
    triage_model = _require_model_setting(data, "triage_model", "gpt-5.4-mini")
    triage_reasoning_effort = _require_reasoning_effort(
        data, "triage_reasoning_effort", "low"
    )
    router_model = _require_model_setting(data, "router_model", "gpt-5.4-mini")
    router_reasoning_effort = _require_reasoning_effort(
        data, "router_reasoning_effort", "low"
    )
    preflight_model = _require_model_setting(data, "preflight_model", "gpt-5.6-luna")
    preflight_reasoning_effort = _require_reasoning_effort(
        data, "preflight_reasoning_effort", "low"
    )
    research_model = _require_model_setting(data, "research_model", "gpt-5.6-luna")
    research_reasoning_effort = _require_reasoning_effort(
        data, "research_reasoning_effort", "medium"
    )
    finalizer_model = _require_model_setting(data, "finalizer_model", primary_model)
    finalizer_reasoning_effort = _require_reasoning_effort(
        data, "finalizer_reasoning_effort", "medium"
    )
    profiles = {
        "quick": _load_orchestration_profile(data, "quick"),
        "routine": _load_orchestration_profile(data, "routine"),
        "standard": _load_orchestration_profile(data, "standard"),
        "deep": _load_orchestration_profile(data, "deep"),
        "high_assurance": _load_orchestration_profile(
            data, "high_assurance", legacy_tier="manuscript"
        ),
    }
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
    task_timeout = _require_int(data, "task_timeout_seconds", 0)
    queue_size = _require_int(data, "queue_size", 20)
    worker_count = _require_int(data, "worker_count", 8)
    max_session_turns = _require_int(data, "max_session_turns", 120)
    temporary_context_retention_days = _require_int(
        data, "temporary_context_retention_days", 14
    )
    memory_max_chars = _require_int(data, "memory_max_chars", 12000)
    codex_network_access = _require_bool(data, "codex_network_access", False)
    admin_full_access = _require_bool(data, "admin_full_access", False)
    admin_auto_approve_actions = _require_bool(
        data, "admin_auto_approve_actions", admin_full_access
    )
    admin_mcp_enabled = _require_bool(data, "admin_mcp_enabled", True)
    admin_delegated_write_access = _require_bool(data, "admin_delegated_write_access", True)
    group_auto_enable_on_admin_address = _require_bool(
        data, "group_auto_enable_on_admin_address", False
    )
    group_member_requests_enabled = _require_bool(data, "group_member_requests_enabled", True)
    group_auto_register_members = _require_bool(data, "group_auto_register_members", False)
    group_require_registered_members = _require_bool(
        data, "group_require_registered_members", False
    )
    group_respond_to_mentions = _require_bool(data, "group_respond_to_mentions", True)
    group_respond_to_bot_replies = _require_bool(data, "group_respond_to_bot_replies", True)
    group_respond_to_addressed_threads = _require_bool(
        data, "group_respond_to_addressed_threads", True
    )
    group_network_access = _require_bool(data, "group_network_access", True)
    group_workspace_write = _require_bool(data, "group_workspace_write", True)
    group_file_delivery_enabled = _require_bool(data, "group_file_delivery_enabled", True)
    attachment_max_bytes = _require_int(data, "attachment_max_bytes", 10_000_000)
    if not 1 <= poll_timeout <= 50:
        raise ConfigError("poll_timeout_seconds must be between 1 and 50")
    if task_timeout != 0 and not 30 <= task_timeout <= 86400:
        raise ConfigError("task_timeout_seconds must be 0 (disabled) or between 30 and 86400")
    if queue_size < 1:
        raise ConfigError("queue_size must be positive")
    if worker_count < 1:
        raise ConfigError("worker_count must be positive")
    if not 5 <= max_session_turns <= 500:
        raise ConfigError("max_session_turns must be between 5 and 500")
    if not 1 <= temporary_context_retention_days <= 90:
        raise ConfigError("temporary_context_retention_days must be between 1 and 90")
    if not 1000 <= memory_max_chars <= 20000:
        raise ConfigError("memory_max_chars must be between 1000 and 20000")
    if not 1_000_000 <= attachment_max_bytes <= 50_000_000:
        raise ConfigError("attachment_max_bytes must be between 1 MB and 50 MB")
    for tier, profile in profiles.items():
        if not 0 <= profile.feedback_iterations <= 5:
            raise ConfigError(f"{tier}_feedback_iterations must be between 0 and 5")
        if profile.feedback_iterations and not profile.uses_validator:
            raise ConfigError(f"{tier} feedback requires {tier}_uses_validator = true")
        if profile.uses_adversarial_review and not profile.feedback_iterations:
            raise ConfigError(
                f"{tier}_uses_adversarial_review requires {tier}_feedback_iterations > 0"
            )
        if (profile.uses_preflight or profile.uses_research) and not profile.uses_validator:
            raise ConfigError(f"{tier} planning and research require {tier}_uses_validator = true")
        if profile.uses_finalizer and not profile.uses_validator:
            raise ConfigError(f"{tier} finalization requires {tier}_uses_validator = true")

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
        quick_model=quick_model,
        quick_reasoning_effort=quick_reasoning_effort,
        routine_model=routine_model,
        routine_reasoning_effort=routine_reasoning_effort,
        primary_model=primary_model,
        primary_reasoning_effort=primary_reasoning_effort,
        rework_model=rework_model,
        rework_reasoning_effort=rework_reasoning_effort,
        validator_model=validator_model,
        validator_reasoning_effort=validator_reasoning_effort,
        feedback_model=feedback_model,
        feedback_reasoning_effort=feedback_reasoning_effort,
        router_model=router_model,
        router_reasoning_effort=router_reasoning_effort,
        triage_model=triage_model,
        triage_reasoning_effort=triage_reasoning_effort,
        preflight_model=preflight_model,
        preflight_reasoning_effort=preflight_reasoning_effort,
        research_model=research_model,
        research_reasoning_effort=research_reasoning_effort,
        finalizer_model=finalizer_model,
        finalizer_reasoning_effort=finalizer_reasoning_effort,
        quick_uses_preflight=profiles["quick"].uses_preflight,
        quick_uses_research=profiles["quick"].uses_research,
        quick_uses_validator=profiles["quick"].uses_validator,
        quick_feedback_iterations=profiles["quick"].feedback_iterations,
        quick_uses_finalizer=profiles["quick"].uses_finalizer,
        quick_uses_adversarial_review=profiles["quick"].uses_adversarial_review,
        routine_uses_preflight=profiles["routine"].uses_preflight,
        routine_uses_research=profiles["routine"].uses_research,
        routine_uses_validator=profiles["routine"].uses_validator,
        routine_feedback_iterations=profiles["routine"].feedback_iterations,
        routine_uses_finalizer=profiles["routine"].uses_finalizer,
        routine_uses_adversarial_review=profiles["routine"].uses_adversarial_review,
        standard_uses_preflight=profiles["standard"].uses_preflight,
        standard_uses_research=profiles["standard"].uses_research,
        standard_uses_validator=profiles["standard"].uses_validator,
        standard_feedback_iterations=profiles["standard"].feedback_iterations,
        standard_uses_finalizer=profiles["standard"].uses_finalizer,
        standard_uses_adversarial_review=profiles["standard"].uses_adversarial_review,
        deep_uses_preflight=profiles["deep"].uses_preflight,
        deep_uses_research=profiles["deep"].uses_research,
        deep_uses_validator=profiles["deep"].uses_validator,
        deep_feedback_iterations=profiles["deep"].feedback_iterations,
        deep_uses_finalizer=profiles["deep"].uses_finalizer,
        deep_uses_adversarial_review=profiles["deep"].uses_adversarial_review,
        high_assurance_uses_preflight=profiles["high_assurance"].uses_preflight,
        high_assurance_uses_research=profiles["high_assurance"].uses_research,
        high_assurance_uses_validator=profiles["high_assurance"].uses_validator,
        high_assurance_feedback_iterations=profiles["high_assurance"].feedback_iterations,
        high_assurance_uses_finalizer=profiles["high_assurance"].uses_finalizer,
        high_assurance_uses_adversarial_review=(
            profiles["high_assurance"].uses_adversarial_review
        ),
        poll_timeout_seconds=poll_timeout,
        task_timeout_seconds=task_timeout,
        queue_size=queue_size,
        worker_count=worker_count,
        max_session_turns=max_session_turns,
        temporary_context_retention_days=temporary_context_retention_days,
        memory_max_chars=memory_max_chars,
        codex_network_access=codex_network_access,
        admin_full_access=admin_full_access,
        admin_auto_approve_actions=admin_auto_approve_actions,
        admin_mcp_enabled=admin_mcp_enabled,
        admin_delegated_write_access=admin_delegated_write_access,
        group_auto_enable_on_admin_address=group_auto_enable_on_admin_address,
        group_member_requests_enabled=group_member_requests_enabled,
        group_auto_register_members=group_auto_register_members,
        group_require_registered_members=group_require_registered_members,
        group_respond_to_mentions=group_respond_to_mentions,
        group_respond_to_bot_replies=group_respond_to_bot_replies,
        group_respond_to_addressed_threads=group_respond_to_addressed_threads,
        group_network_access=group_network_access,
        group_workspace_write=group_workspace_write,
        group_file_delivery_enabled=group_file_delivery_enabled,
        attachment_max_bytes=attachment_max_bytes,
        read_only_roots=tuple(read_only_roots),
        delegated_roots=tuple(delegated_roots),
        mcp_known_servers=tuple(raw_known_servers),
        mcp_allowed_tools=tuple(allowed_tools),
        agent_repository_root=agent_repository_root,
    )


def set_workspace_directory(directory: Path, *, config_path: Path | None = None) -> Config:
    """Persist a validated workspace directory without rewriting unrelated settings."""
    workspace = directory.expanduser().resolve()
    if not workspace.is_dir():
        raise ConfigError(f"workspace directory must exist: {workspace}")
    path = config_path or Path(os.environ.get("TELEGRAM_CODEX_CONFIG", DEFAULT_CONFIG_PATH))
    try:
        original = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"cannot read config: {exc}") from exc
    updated, replacements = re.subn(
        r'(?m)^workdir\s*=\s*"(?:[^"\\\\]|\\\\.)*"\s*$',
        f"workdir = {json.dumps(str(workspace))}",
        original,
    )
    if replacements != 1:
        raise ConfigError("config must contain exactly one quoted workdir setting")
    if updated == original:
        return load_config(path)
    atomic_write_text(path, updated)
    try:
        return load_config(path)
    except ConfigError:
        atomic_write_text(path, original)
        raise


def set_model_assignments(
    *,
    routine_model: str,
    primary_model: str,
    validator_model: str,
    preflight_model: str,
    config_path: Path | None = None,
    routine_reasoning_effort: str | None = None,
    primary_reasoning_effort: str | None = None,
    rework_model: str | None = None,
    rework_reasoning_effort: str | None = None,
    validator_reasoning_effort: str | None = None,
    feedback_model: str | None = None,
    feedback_reasoning_effort: str | None = None,
    router_model: str | None = None,
    router_reasoning_effort: str | None = None,
    triage_model: str | None = None,
    triage_reasoning_effort: str | None = None,
    preflight_reasoning_effort: str | None = None,
    research_model: str | None = None,
    research_reasoning_effort: str | None = None,
    finalizer_model: str | None = None,
    finalizer_reasoning_effort: str | None = None,
    quick_model: str | None = None,
    quick_reasoning_effort: str | None = None,
) -> Config:
    """Persist the role-specific model routing without rewriting unrelated settings."""
    path = config_path or Path(os.environ.get("TELEGRAM_CODEX_CONFIG", DEFAULT_CONFIG_PATH))
    current = load_config(path)
    assignments = {
        "quick_model": quick_model or current.quick_model,
        "quick_reasoning_effort": quick_reasoning_effort or current.quick_reasoning_effort,
        "routine_model": routine_model,
        "routine_reasoning_effort": routine_reasoning_effort or current.routine_reasoning_effort,
        "primary_model": primary_model,
        "primary_reasoning_effort": primary_reasoning_effort or current.primary_reasoning_effort,
        "rework_model": rework_model or current.rework_model,
        "rework_reasoning_effort": rework_reasoning_effort or current.rework_reasoning_effort,
        "validator_model": validator_model,
        "validator_reasoning_effort": validator_reasoning_effort or current.validator_reasoning_effort,
        "feedback_model": feedback_model or current.feedback_model,
        "feedback_reasoning_effort": feedback_reasoning_effort or current.feedback_reasoning_effort,
        "router_model": router_model or current.router_model,
        "router_reasoning_effort": router_reasoning_effort or current.router_reasoning_effort,
        "triage_model": triage_model or current.triage_model,
        "triage_reasoning_effort": triage_reasoning_effort or current.triage_reasoning_effort,
        "preflight_model": preflight_model,
        "preflight_reasoning_effort": preflight_reasoning_effort or current.preflight_reasoning_effort,
        "research_model": research_model or current.research_model,
        "research_reasoning_effort": research_reasoning_effort or current.research_reasoning_effort,
        "finalizer_model": finalizer_model or current.finalizer_model,
        "finalizer_reasoning_effort": finalizer_reasoning_effort or current.finalizer_reasoning_effort,
    }
    model_settings = {
        name: value for name, value in assignments.items() if name.endswith("_model")
    }
    if any(not _MODEL_ID_PATTERN.fullmatch(model) for model in model_settings.values()):
        raise ConfigError("model assignments must be valid model identifiers")
    if any(
        effort not in _REASONING_EFFORTS
        for name, effort in assignments.items()
        if name.endswith("_reasoning_effort")
    ):
        allowed = ", ".join(sorted(_REASONING_EFFORTS))
        raise ConfigError(f"reasoning efforts must be one of: {allowed}")
    try:
        original = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"cannot read config: {exc}") from exc
    updated = original
    missing_settings: list[str] = []
    for setting, value in assignments.items():
        updated, replacements = re.subn(
            rf'(?m)^{setting}\s*=\s*"(?:[^"\\\\]|\\\\.)*"\s*$',
            f"{setting} = {json.dumps(value)}",
            updated,
        )
        if replacements > 1:
            raise ConfigError(f"config must contain exactly one quoted {setting} setting")
        if replacements == 0:
            missing_settings.append(f"{setting} = {json.dumps(value)}")
    if missing_settings:
        first_table = re.search(r"(?m)^\[", updated)
        if first_table is None:
            updated = updated.rstrip() + "\n" + "\n".join(missing_settings) + "\n"
        else:
            updated = (
                updated[: first_table.start()].rstrip()
                + "\n"
                + "\n".join(missing_settings)
                + "\n\n"
                + updated[first_table.start() :]
            )
    if updated == original:
        return load_config(path)
    atomic_write_text(path, updated)
    try:
        return load_config(path)
    except ConfigError:
        atomic_write_text(path, original)
        raise


def set_security_settings(
    *,
    network_access: bool,
    admin_full_access: bool,
    admin_auto_approve_actions: bool,
    admin_mcp_enabled: bool,
    admin_delegated_write_access: bool,
    group_auto_enable_on_admin_address: bool,
    group_member_requests_enabled: bool,
    group_auto_register_members: bool,
    group_require_registered_members: bool,
    group_respond_to_mentions: bool,
    group_respond_to_bot_replies: bool,
    group_respond_to_addressed_threads: bool,
    group_network_access: bool,
    group_workspace_write: bool,
    group_file_delivery_enabled: bool,
    config_path: Path | None = None,
) -> Config:
    """Persist the administrator and non-administrator group permission switches."""
    values = (
        network_access,
        admin_full_access,
        admin_auto_approve_actions,
        admin_mcp_enabled,
        admin_delegated_write_access,
        group_auto_enable_on_admin_address,
        group_member_requests_enabled,
        group_auto_register_members,
        group_require_registered_members,
        group_respond_to_mentions,
        group_respond_to_bot_replies,
        group_respond_to_addressed_threads,
        group_network_access,
        group_workspace_write,
        group_file_delivery_enabled,
    )
    if any(not isinstance(value, bool) for value in values):
        raise ConfigError("security settings must be true or false")
    path = config_path or Path(os.environ.get("TELEGRAM_CODEX_CONFIG", DEFAULT_CONFIG_PATH))
    try:
        original = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"cannot read config: {exc}") from exc
    updated = original
    assignments = {
        "codex_network_access": network_access,
        "admin_full_access": admin_full_access,
        "admin_auto_approve_actions": admin_auto_approve_actions,
        "admin_mcp_enabled": admin_mcp_enabled,
        "admin_delegated_write_access": admin_delegated_write_access,
        "group_auto_enable_on_admin_address": group_auto_enable_on_admin_address,
        "group_member_requests_enabled": group_member_requests_enabled,
        "group_auto_register_members": group_auto_register_members,
        "group_require_registered_members": group_require_registered_members,
        "group_respond_to_mentions": group_respond_to_mentions,
        "group_respond_to_bot_replies": group_respond_to_bot_replies,
        "group_respond_to_addressed_threads": group_respond_to_addressed_threads,
        "group_network_access": group_network_access,
        "group_workspace_write": group_workspace_write,
        "group_file_delivery_enabled": group_file_delivery_enabled,
    }
    missing_settings: list[str] = []
    for setting, value in assignments.items():
        rendered = str(value).lower()
        updated, replacements = re.subn(
            rf"(?m)^{setting}\s*=\s*(?:true|false)\s*$",
            f"{setting} = {rendered}",
            updated,
        )
        if replacements > 1:
            raise ConfigError(f"config must contain exactly one {setting} setting")
        if replacements == 0:
            missing_settings.append(f"{setting} = {rendered}")
    if missing_settings:
        first_table = re.search(r"(?m)^\[", updated)
        if first_table is None:
            updated = updated.rstrip() + "\n" + "\n".join(missing_settings) + "\n"
        else:
            updated = (
                updated[: first_table.start()].rstrip()
                + "\n"
                + "\n".join(missing_settings)
                + "\n\n"
                + updated[first_table.start() :]
            )
    if updated == original:
        return load_config(path)
    atomic_write_text(path, updated)
    try:
        return load_config(path)
    except ConfigError:
        atomic_write_text(path, original)
        raise


def set_orchestration(
    *,
    profiles: dict[str, OrchestrationProfile],
    config_path: Path | None = None,
) -> Config:
    """Persist the task-tier orchestration without rewriting unrelated settings."""
    if set(profiles) != set(ORCHESTRATION_TIERS):
        raise ConfigError("orchestration must define every task tier exactly once")
    assignments: dict[str, bool | int] = {
        f"{tier}_uses_preflight": profile.uses_preflight
        for tier, profile in profiles.items()
    }
    assignments.update(
        {
            f"{tier}_uses_research": profile.uses_research
            for tier, profile in profiles.items()
        }
    )
    assignments.update(
        {
            f"{tier}_uses_validator": profile.uses_validator
            for tier, profile in profiles.items()
        }
    )
    assignments.update(
        {
            f"{tier}_feedback_iterations": profile.feedback_iterations
            for tier, profile in profiles.items()
        }
    )
    assignments.update(
        {
            f"{tier}_uses_finalizer": profile.uses_finalizer
            for tier, profile in profiles.items()
        }
    )
    assignments.update(
        {
            f"{tier}_uses_adversarial_review": profile.uses_adversarial_review
            for tier, profile in profiles.items()
        }
    )
    stage_values = [
        value
        for name, value in assignments.items()
        if name.endswith(
            (
                "uses_preflight",
                "uses_research",
                "uses_validator",
                "uses_finalizer",
                "uses_adversarial_review",
            )
        )
    ]
    if any(not isinstance(value, bool) for value in stage_values):
        raise ConfigError("orchestration stage settings must be true or false")
    if any(
        not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 5
        for name, value in assignments.items()
        if name.endswith("feedback_iterations")
    ):
        raise ConfigError("orchestration feedback iterations must be between 0 and 5")
    for tier, profile in profiles.items():
        if (
            profile.feedback_iterations
            and not profile.uses_validator
        ):
            raise ConfigError(f"{tier} feedback requires validation")
        if profile.uses_adversarial_review and not profile.feedback_iterations:
            raise ConfigError(f"{tier} adversarial review requires at least one rework loop")
        if (profile.uses_preflight or profile.uses_research) and not profile.uses_validator:
            raise ConfigError(f"{tier} planning and research require validation")
        if profile.uses_finalizer and not profile.uses_validator:
            raise ConfigError(f"{tier} finalization requires validation")
    path = config_path or Path(os.environ.get("TELEGRAM_CODEX_CONFIG", DEFAULT_CONFIG_PATH))
    try:
        original = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"cannot read config: {exc}") from exc
    updated = original
    updated = re.sub(
        r"(?m)^manuscript_(?:uses_preflight|uses_validator|feedback_iterations)\s*=\s*(?:true|false|\d+)\s*\n?",
        "",
        updated,
    )
    missing_settings: list[str] = []
    for setting, value in assignments.items():
        rendered = str(value).lower()
        updated, replacements = re.subn(
            rf"(?m)^{setting}\s*=\s*(?:true|false|\d+)\s*$",
            f"{setting} = {rendered}",
            updated,
        )
        if replacements > 1:
            raise ConfigError(f"config must contain exactly one {setting} setting")
        if replacements == 0:
            missing_settings.append(f"{setting} = {rendered}")
    if missing_settings:
        first_table = re.search(r"(?m)^\[", updated)
        if first_table is None:
            updated = updated.rstrip() + "\n" + "\n".join(missing_settings) + "\n"
        else:
            updated = (
                updated[: first_table.start()].rstrip()
                + "\n"
                + "\n".join(missing_settings)
                + "\n\n"
                + updated[first_table.start() :]
            )
    if updated == original:
        return load_config(path)
    atomic_write_text(path, updated)
    try:
        return load_config(path)
    except ConfigError:
        atomic_write_text(path, original)
        raise


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
            'quick_model = "gpt-5.4-mini"',
            'quick_reasoning_effort = "low"',
            'routine_model = "gpt-5.6-luna"',
            'routine_reasoning_effort = "low"',
            'primary_model = "gpt-5.6-sol"',
            'primary_reasoning_effort = "high"',
            'rework_model = "gpt-5.6-sol"',
            'rework_reasoning_effort = "high"',
            'validator_model = "gpt-5.6-terra"',
            'validator_reasoning_effort = "high"',
            'feedback_model = "gpt-5.6-terra"',
            'feedback_reasoning_effort = "high"',
            'router_model = "gpt-5.4-mini"',
            'router_reasoning_effort = "low"',
            'triage_model = "gpt-5.4-mini"',
            'triage_reasoning_effort = "low"',
            'preflight_model = "gpt-5.6-luna"',
            'preflight_reasoning_effort = "low"',
            'research_model = "gpt-5.6-luna"',
            'research_reasoning_effort = "medium"',
            'finalizer_model = "gpt-5.6-sol"',
            'finalizer_reasoning_effort = "medium"',
            "quick_uses_preflight = false",
            "quick_uses_research = false",
            "quick_uses_validator = false",
            "quick_feedback_iterations = 0",
            "quick_uses_finalizer = false",
            "quick_uses_adversarial_review = false",
            "routine_uses_preflight = false",
            "routine_uses_research = false",
            "routine_uses_validator = false",
            "routine_feedback_iterations = 0",
            "routine_uses_finalizer = false",
            "routine_uses_adversarial_review = false",
            "standard_uses_preflight = false",
            "standard_uses_research = false",
            "standard_uses_validator = true",
            "standard_feedback_iterations = 0",
            "standard_uses_finalizer = true",
            "standard_uses_adversarial_review = false",
            "deep_uses_preflight = true",
            "deep_uses_research = false",
            "deep_uses_validator = true",
            "deep_feedback_iterations = 1",
            "deep_uses_finalizer = true",
            "deep_uses_adversarial_review = true",
            "high_assurance_uses_preflight = true",
            "high_assurance_uses_research = true",
            "high_assurance_uses_validator = true",
            "high_assurance_feedback_iterations = 2",
            "high_assurance_uses_finalizer = true",
            "high_assurance_uses_adversarial_review = true",
            "poll_timeout_seconds = 30",
            "task_timeout_seconds = 0",
            "queue_size = 20",
            "worker_count = 8",
            "max_session_turns = 120",
            "temporary_context_retention_days = 14",
            "memory_max_chars = 12000",
            "codex_network_access = false",
            "admin_full_access = false",
            "admin_auto_approve_actions = false",
            "admin_mcp_enabled = true",
            "admin_delegated_write_access = true",
            "group_auto_enable_on_admin_address = false",
            "group_member_requests_enabled = true",
            "group_auto_register_members = false",
            "group_require_registered_members = false",
            "group_respond_to_mentions = true",
            "group_respond_to_bot_replies = true",
            "group_respond_to_addressed_threads = true",
            "group_network_access = true",
            "group_workspace_write = true",
            "group_file_delivery_enabled = true",
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
