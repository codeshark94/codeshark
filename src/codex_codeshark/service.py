from __future__ import annotations

import hashlib
import os
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .automation import AgentStore
from .config import PROJECT_ROOT
from .secure_io import (
    atomic_write_bytes,
    ensure_private_directory,
    ensure_private_file,
    read_private_bytes,
)

LABEL = "com.codeshark.agent"
MENU_LABEL = "com.codeshark.status"
PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
MENU_PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{MENU_LABEL}.plist"
INSTALL_ROOT = Path.home() / "Library" / "Application Support" / "Codex-codeshark" / "app"
SOURCE_ROOT = Path(__file__).resolve().parents[1]
_TOKEN_PATTERN = re.compile(r"\b[0-9]{6,}:[A-Za-z0-9_-]+\b")
_DEFERRED_RESTART_MARKER = ".restart-pending"
_DEFERRED_RESTART_CLAIM = ".restart-applying"


class ServiceError(RuntimeError):
    pass


@dataclass(frozen=True)
class ServiceStatus:
    running: bool
    state: str
    pid: int | None
    detail: str = ""


def _domain() -> str:
    return f"gui/{os.getuid()}"


def _service_target() -> str:
    return f"{_domain()}/{LABEL}"


def _menu_service_target() -> str:
    return f"{_domain()}/{MENU_LABEL}"


def _menu_plist_path(agent_plist_path: Path) -> Path:
    if agent_plist_path == PLIST_PATH:
        return MENU_PLIST_PATH
    return agent_plist_path.with_name(f"{MENU_LABEL}.plist")


def _restart_marker_paths(project_root: Path) -> tuple[Path, Path]:
    runtime = project_root / "runtime"
    return runtime / _DEFERRED_RESTART_MARKER, runtime / _DEFERRED_RESTART_CLAIM


def deferred_restart_requested(*, project_root: Path = PROJECT_ROOT) -> bool:
    pending, applying = _restart_marker_paths(project_root)
    for marker in (pending, applying):
        if marker.exists() or marker.is_symlink():
            ensure_private_file(marker)
            return True
    return False


def request_deferred_restart(*, project_root: Path = PROJECT_ROOT) -> None:
    runtime = project_root / "runtime"
    ensure_private_directory(runtime)
    pending, applying = _restart_marker_paths(project_root)
    if applying.exists() or applying.is_symlink():
        ensure_private_file(applying)
        return
    atomic_write_bytes(pending, b"pending\n")


def _restore_deferred_restart(claim: Path, pending: Path) -> None:
    if claim.exists() or claim.is_symlink():
        ensure_private_file(claim)
        os.replace(claim, pending)


def apply_deferred_restart_if_idle(
    *,
    project_root: Path = PROJECT_ROOT,
    restart: Callable[..., ServiceStatus] | None = None,
) -> ServiceStatus | None:
    """Restart only after every active task has reached a terminal state."""
    pending, claim = _restart_marker_paths(project_root)
    if not deferred_restart_requested(project_root=project_root):
        return None
    if AgentStore(project_root / "runtime" / "agent.db").running_count():
        return None
    try:
        os.replace(pending, claim)
    except FileNotFoundError:
        return None
    try:
        restart_operation = restart or restart_service
        status = restart_operation(project_root=project_root)
        if not status.running:
            raise ServiceError(status.detail or "service did not restart")
    except Exception:
        _restore_deferred_restart(claim, pending)
        raise
    claim.unlink(missing_ok=True)
    return status


def wait_for_deferred_restart(
    *,
    project_root: Path = PROJECT_ROOT,
    poll_seconds: float = 0.5,
) -> ServiceStatus | None:
    while deferred_restart_requested(project_root=project_root):
        status = apply_deferred_restart_if_idle(project_root=project_root)
        if status is not None:
            return status
        time.sleep(poll_seconds)
    return None


def restart_when_idle(*, project_root: Path = PROJECT_ROOT) -> ServiceStatus | None:
    """Restart now when idle, otherwise let a detached monitor restart after active work."""
    request_deferred_restart(project_root=project_root)
    status = apply_deferred_restart_if_idle(project_root=project_root)
    if status is not None:
        return status
    try:
        subprocess.Popen(
            [sys.executable, "-m", "codex_codeshark", "apply-pending-restart"],
            cwd=project_root,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError:
        pending, _ = _restart_marker_paths(project_root)
        pending.unlink(missing_ok=True)
        raise
    return None


def _wait_for_status(*, running: bool, timeout: float = 5.0) -> ServiceStatus:
    deadline = time.monotonic() + timeout
    status = service_status()
    while status.running != running and time.monotonic() < deadline:
        time.sleep(0.1)
        status = service_status()
    return status


def _source_digest(source_root: Path, config_data: bytes) -> str:
    package = source_root / "codex_codeshark"
    if package.is_symlink() or not package.is_dir():
        raise ServiceError(f"Codex-codeshark package source is missing: {package}")
    digest = hashlib.sha256()
    files = [
        path
        for path in package.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix not in {".pyc", ".pyo"}
    ]
    for path in sorted(files, key=lambda item: item.relative_to(package).as_posix()):
        if path.is_symlink():
            raise ServiceError(f"service source must not contain symbolic links: {path}")
        relative = path.relative_to(package).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        digest.update(path.read_bytes())
    if not files:
        raise ServiceError(f"Codex-codeshark package source is empty: {package}")
    digest.update(b"\0config.local.toml\0")
    digest.update(config_data)
    return digest.hexdigest()


def _deploy_source(
    *,
    source_root: Path,
    config_path: Path,
    install_root: Path,
) -> tuple[Path, Path]:
    ensure_private_directory(install_root)
    ensure_private_file(config_path)
    config_data = read_private_bytes(config_path, max_bytes=1_000_000)
    version_root = install_root / _source_digest(source_root, config_data)
    installed_source = version_root / "src"
    installed_config = version_root / "config.local.toml"
    if (
        (installed_source / "codex_codeshark" / "__main__.py").is_file()
        and installed_config.is_file()
    ):
        return installed_source, installed_config
    staging = Path(tempfile.mkdtemp(prefix=".install-", dir=install_root))
    try:
        target = staging / "src" / "codex_codeshark"
        target.parent.mkdir(mode=0o700)
        shutil.copytree(
            source_root / "codex_codeshark",
            target,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
        )
        (staging / "config.local.toml").write_bytes(config_data)
        for path in staging.rglob("*"):
            if path.is_symlink():
                raise ServiceError(f"deployed service source contains a symbolic link: {path}")
            path.chmod(0o700 if path.is_dir() else 0o600)
        try:
            os.replace(staging, version_root)
        except FileExistsError:
            pass
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    if not (
        (installed_source / "codex_codeshark" / "__main__.py").is_file()
        and installed_config.is_file()
    ):
        raise ServiceError("failed to deploy the versioned service source")
    return installed_source, installed_config


def _harden_runtime(runtime: Path) -> None:
    ensure_private_directory(runtime)
    for path in runtime.rglob("*"):
        if path.is_symlink():
            raise ServiceError(f"runtime storage must not contain symbolic links: {path}")
        path.chmod(0o700 if path.is_dir() else 0o600)


def _payload(
    project_root: Path,
    python: str,
    installed_source: Path,
    installed_config: Path,
) -> dict:
    runtime = project_root / "runtime"
    return {
        "Label": LABEL,
        "ProgramArguments": [python, "-m", "codex_codeshark", "run"],
        "WorkingDirectory": str(installed_source.parent),
        "EnvironmentVariables": {
            "PYTHONPATH": str(installed_source),
            "CODEX_CODESHARK_HOME": str(project_root),
            "TELEGRAM_CODEX_CONFIG": str(installed_config),
            "PYTHONNOUSERSITE": "1",
            "PYTHONSAFEPATH": "1",
            "PATH": "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin",
        },
        "Umask": 0o077,
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": 10,
        "StandardOutPath": str(runtime / "agent.out.log"),
        "StandardErrorPath": str(runtime / "agent.err.log"),
    }


def _build_menu_bar_agent(installed_source: Path) -> tuple[Path, Path]:
    source = installed_source / "codex_codeshark" / "menu_bar.swift"
    icon = installed_source / "codex_codeshark" / "codeshark-menubar-template.png"
    if not source.is_file() or not icon.is_file():
        raise ServiceError("Codeshark menu bar source is missing from the service package")
    executable = installed_source.parent / "CodesharkMenu"
    result = subprocess.run(
        ["/usr/bin/swiftc", str(source), "-o", str(executable)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "swiftc failed"
        raise ServiceError(f"could not build the Codeshark menu bar icon: {detail}")
    if executable.is_file():
        executable.chmod(0o700)
    return executable, icon


def _menu_payload(project_root: Path, executable: Path, icon: Path) -> dict:
    runtime = project_root / "runtime"
    return {
        "Label": MENU_LABEL,
        "ProgramArguments": [str(executable), str(project_root), str(icon)],
        "WorkingDirectory": str(executable.parent),
        "Umask": 0o077,
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": 10,
        "StandardOutPath": str(runtime / "menu.out.log"),
        "StandardErrorPath": str(runtime / "menu.err.log"),
    }


def install_service(
    *,
    project_root: Path = PROJECT_ROOT,
    plist_path: Path = PLIST_PATH,
    python: str = sys.executable,
    install_root: Path = INSTALL_ROOT,
    source_root: Path = SOURCE_ROOT,
    install_menu: bool = True,
) -> Path:
    config_path = project_root / "config.local.toml"
    if config_path.is_symlink() or not config_path.is_file():
        raise ServiceError("config.local.toml is missing; run setup first")
    runtime = project_root / "runtime"
    _harden_runtime(runtime)
    ensure_private_directory(plist_path.parent)
    installed_source, installed_config = _deploy_source(
        source_root=source_root,
        config_path=config_path,
        install_root=install_root,
    )
    menu_plist_path = _menu_plist_path(plist_path)
    atomic_write_bytes(
        plist_path,
        plistlib.dumps(
            _payload(project_root, python, installed_source, installed_config),
            sort_keys=False,
        ),
    )
    if install_menu:
        menu_executable, menu_icon = _build_menu_bar_agent(installed_source)
        atomic_write_bytes(
            menu_plist_path,
            plistlib.dumps(_menu_payload(project_root, menu_executable, menu_icon), sort_keys=False),
        )

    subprocess.run(
        ["/bin/launchctl", "bootout", _domain(), str(plist_path)],
        capture_output=True,
        check=False,
    )
    if install_menu:
        subprocess.run(
            ["/bin/launchctl", "bootout", _domain(), str(menu_plist_path)],
            capture_output=True,
            check=False,
        )
    result = subprocess.run(
        ["/bin/launchctl", "bootstrap", _domain(), str(plist_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise ServiceError(result.stderr.strip() or result.stdout.strip() or "launchctl bootstrap failed")
    subprocess.run(
        ["/bin/launchctl", "kickstart", "-k", _service_target()],
        capture_output=True,
        check=False,
    )
    if install_menu:
        result = subprocess.run(
            ["/bin/launchctl", "bootstrap", _domain(), str(menu_plist_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise ServiceError(
                result.stderr.strip() or result.stdout.strip() or "launchctl menu bootstrap failed"
            )
        subprocess.run(
            ["/bin/launchctl", "kickstart", "-k", _menu_service_target()],
            capture_output=True,
            check=False,
        )
    return plist_path


def refresh_menu_bar(
    *,
    project_root: Path = PROJECT_ROOT,
    plist_path: Path = PLIST_PATH,
    install_root: Path = INSTALL_ROOT,
    source_root: Path = SOURCE_ROOT,
) -> Path:
    config_path = project_root / "config.local.toml"
    if config_path.is_symlink() or not config_path.is_file():
        raise ServiceError("config.local.toml is missing; run setup first")
    runtime = project_root / "runtime"
    _harden_runtime(runtime)
    ensure_private_directory(plist_path.parent)
    installed_source, _ = _deploy_source(
        source_root=source_root,
        config_path=config_path,
        install_root=install_root,
    )
    menu_executable, menu_icon = _build_menu_bar_agent(installed_source)
    menu_plist_path = _menu_plist_path(plist_path)
    atomic_write_bytes(
        menu_plist_path,
        plistlib.dumps(_menu_payload(project_root, menu_executable, menu_icon), sort_keys=False),
    )
    subprocess.run(
        ["/bin/launchctl", "bootout", _domain(), str(menu_plist_path)],
        capture_output=True,
        check=False,
    )
    result = subprocess.run(
        ["/bin/launchctl", "bootstrap", _domain(), str(menu_plist_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise ServiceError(
            result.stderr.strip() or result.stdout.strip() or "launchctl menu bootstrap failed"
        )
    subprocess.run(
        ["/bin/launchctl", "kickstart", "-k", _menu_service_target()],
        capture_output=True,
        check=False,
    )
    return menu_plist_path


def uninstall_service(*, plist_path: Path = PLIST_PATH) -> None:
    menu_plist_path = _menu_plist_path(plist_path)
    subprocess.run(
        ["/bin/launchctl", "bootout", _domain(), str(plist_path)],
        capture_output=True,
        check=False,
    )
    subprocess.run(
        ["/bin/launchctl", "bootout", _domain(), str(menu_plist_path)],
        capture_output=True,
        check=False,
    )
    if plist_path.exists():
        plist_path.unlink()
    if menu_plist_path.exists():
        menu_plist_path.unlink()


def start_service(
    *,
    project_root: Path = PROJECT_ROOT,
    plist_path: Path = PLIST_PATH,
    python: str = sys.executable,
    install_root: Path = INSTALL_ROOT,
) -> ServiceStatus:
    install_service(
        project_root=project_root,
        plist_path=plist_path,
        python=python,
        install_root=install_root,
    )
    return _wait_for_status(running=True)


def stop_service(*, plist_path: Path = PLIST_PATH) -> ServiceStatus:
    menu_plist_path = _menu_plist_path(plist_path)
    subprocess.run(
        ["/bin/launchctl", "bootout", _domain(), str(plist_path)],
        capture_output=True,
        check=False,
    )
    subprocess.run(
        ["/bin/launchctl", "bootout", _domain(), str(menu_plist_path)],
        capture_output=True,
        check=False,
    )
    return _wait_for_status(running=False)


def restart_service(
    *,
    project_root: Path = PROJECT_ROOT,
    plist_path: Path = PLIST_PATH,
    python: str = sys.executable,
    install_root: Path = INSTALL_ROOT,
    refresh_menu: bool = False,
) -> ServiceStatus:
    install_service(
        project_root=project_root,
        plist_path=plist_path,
        python=python,
        install_root=install_root,
        install_menu=refresh_menu or not _menu_plist_path(plist_path).is_file(),
    )
    return _wait_for_status(running=True)


def service_status() -> ServiceStatus:
    result = subprocess.run(
        ["/bin/launchctl", "print", _service_target()],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        return ServiceStatus(False, "stopped", None, detail)
    state_match = re.search(r"^\s*state = (\S+)", result.stdout, re.MULTILINE)
    pid_match = re.search(r"^\s*pid = ([0-9]+)", result.stdout, re.MULTILINE)
    state = state_match.group(1) if state_match else "unknown"
    pid = int(pid_match.group(1)) if pid_match else None
    return ServiceStatus(state == "running" and pid is not None, state, pid)


def read_logs(
    lines: int = 100,
    *,
    project_root: Path = PROJECT_ROOT,
) -> str:
    limit = max(1, min(lines, 1000))
    sections: list[str] = []
    for name in ("agent.out.log", "agent.err.log", "menu.out.log", "menu.err.log"):
        path = project_root / "runtime" / name
        if not path.is_file():
            continue
        with path.open("rb") as stream:
            stream.seek(0, os.SEEK_END)
            size = stream.tell()
            start = max(0, size - 1_000_000)
            stream.seek(start)
            content = stream.read().decode("utf-8", errors="replace").splitlines()
        if start and content:
            content = content[1:]
        content = content[-limit:]
        sanitized = _TOKEN_PATTERN.sub("[REDACTED_TELEGRAM_TOKEN]", "\n".join(content))
        sanitized = sanitized.replace(str(Path.home()), "~")
        sections.append(f"== {name} ==\n{sanitized}".rstrip())
    return "\n\n".join(sections) if sections else "No service logs were found."
