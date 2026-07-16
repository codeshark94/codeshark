from __future__ import annotations

import os
import subprocess
from pathlib import Path


LABEL = "com.codeshark.agent"
PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def main() -> int:
    domain = f"gui/{os.getuid()}"
    subprocess.run(["/bin/launchctl", "bootout", domain, str(PLIST_PATH)], check=False, capture_output=True)
    if PLIST_PATH.exists():
        PLIST_PATH.unlink()
    print("LaunchAgent 제거 완료")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
