from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from codex_codeshark.service import uninstall_service  # noqa: E402


def main() -> int:
    uninstall_service()
    print("LaunchAgent removed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
