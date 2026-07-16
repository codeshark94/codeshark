from __future__ import annotations

import os
import plistlib
import subprocess
import sys
from pathlib import Path


LABEL = "com.codeshark.agent"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def main() -> int:
    if not (PROJECT_ROOT / "config.local.toml").is_file():
        print("config.local.toml is missing. Run setup first.")
        return 1

    runtime = PROJECT_ROOT / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "Label": LABEL,
        "ProgramArguments": [sys.executable, "-m", "codex_codeshark", "run"],
        "WorkingDirectory": str(PROJECT_ROOT),
        "EnvironmentVariables": {
            "PYTHONPATH": str(PROJECT_ROOT / "src"),
            "PATH": "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin",
        },
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": 10,
        "StandardOutPath": str(runtime / "agent.out.log"),
        "StandardErrorPath": str(runtime / "agent.err.log"),
    }
    temporary = PLIST_PATH.with_suffix(".plist.tmp")
    with temporary.open("wb") as handle:
        plistlib.dump(payload, handle, sort_keys=False)
    temporary.chmod(0o600)
    os.replace(temporary, PLIST_PATH)

    domain = f"gui/{os.getuid()}"
    subprocess.run(["/bin/launchctl", "bootout", domain, str(PLIST_PATH)], check=False, capture_output=True)
    result = subprocess.run(
        ["/bin/launchctl", "bootstrap", domain, str(PLIST_PATH)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        print(result.stderr.strip() or result.stdout.strip())
        return result.returncode
    subprocess.run(["/bin/launchctl", "kickstart", "-k", f"{domain}/{LABEL}"], check=False)
    print(f"LaunchAgent installed: {PLIST_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
