from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from codex_codeshark.service import ServiceError, install_service  # noqa: E402


def main() -> int:
    try:
        path = install_service()
    except ServiceError as exc:
        print(exc)
        return 1
    print(f"LaunchAgent installed: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
