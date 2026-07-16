from __future__ import annotations

import os
import plistlib
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from .config import PROJECT_ROOT

LABEL = "com.codeshark.agent"
PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
_TOKEN_PATTERN = re.compile(r"\b[0-9]{6,}:[A-Za-z0-9_-]+\b")


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


def _wait_for_status(*, running: bool, timeout: float = 5.0) -> ServiceStatus:
    deadline = time.monotonic() + timeout
    status = service_status()
    while status.running != running and time.monotonic() < deadline:
        time.sleep(0.1)
        status = service_status()
    return status


def _payload(project_root: Path, python: str) -> dict:
    runtime = project_root / "runtime"
    return {
        "Label": LABEL,
        "ProgramArguments": [python, "-m", "codex_codeshark", "run"],
        "WorkingDirectory": str(project_root),
        "EnvironmentVariables": {
            "PYTHONPATH": str(project_root / "src"),
            "PATH": "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin",
        },
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": 10,
        "StandardOutPath": str(runtime / "agent.out.log"),
        "StandardErrorPath": str(runtime / "agent.err.log"),
    }


def install_service(
    *,
    project_root: Path = PROJECT_ROOT,
    plist_path: Path = PLIST_PATH,
    python: str = sys.executable,
) -> Path:
    if not (project_root / "config.local.toml").is_file():
        raise ServiceError("config.local.toml is missing; run setup first")
    runtime = project_root / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = plist_path.with_suffix(plist_path.suffix + ".tmp")
    with temporary.open("wb") as handle:
        plistlib.dump(_payload(project_root, python), handle, sort_keys=False)
    temporary.chmod(0o600)
    os.replace(temporary, plist_path)

    subprocess.run(
        ["/bin/launchctl", "bootout", _domain(), str(plist_path)],
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
    return plist_path


def uninstall_service(*, plist_path: Path = PLIST_PATH) -> None:
    subprocess.run(
        ["/bin/launchctl", "bootout", _domain(), str(plist_path)],
        capture_output=True,
        check=False,
    )
    if plist_path.exists():
        plist_path.unlink()


def start_service(
    *,
    project_root: Path = PROJECT_ROOT,
    plist_path: Path = PLIST_PATH,
    python: str = sys.executable,
) -> ServiceStatus:
    if not plist_path.is_file():
        install_service(project_root=project_root, plist_path=plist_path, python=python)
        return _wait_for_status(running=True)
    current = service_status()
    if not current.running:
        result = subprocess.run(
            ["/bin/launchctl", "bootstrap", _domain(), str(plist_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise ServiceError(result.stderr.strip() or result.stdout.strip() or "launchctl bootstrap failed")
    subprocess.run(
        ["/bin/launchctl", "kickstart", _service_target()],
        capture_output=True,
        check=False,
    )
    return _wait_for_status(running=True)


def stop_service(*, plist_path: Path = PLIST_PATH) -> ServiceStatus:
    subprocess.run(
        ["/bin/launchctl", "bootout", _domain(), str(plist_path)],
        capture_output=True,
        check=False,
    )
    return _wait_for_status(running=False)


def restart_service(
    *,
    project_root: Path = PROJECT_ROOT,
    plist_path: Path = PLIST_PATH,
    python: str = sys.executable,
) -> ServiceStatus:
    if not plist_path.is_file():
        install_service(project_root=project_root, plist_path=plist_path, python=python)
    else:
        current = service_status()
        if current.running:
            subprocess.run(
                ["/bin/launchctl", "kickstart", "-k", _service_target()],
                capture_output=True,
                check=False,
            )
        else:
            return start_service(project_root=project_root, plist_path=plist_path, python=python)
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
    for name in ("agent.out.log", "agent.err.log"):
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
