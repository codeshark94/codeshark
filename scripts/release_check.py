#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FILES = (
    "README.md",
    "CHANGELOG.md",
    "LICENSE",
    "SECURITY.md",
    "CONTRIBUTING.md",
    "CODE_OF_CONDUCT.md",
    "MANIFEST.in",
    "assets/codeshark-mascot.png",
)


def check_release(tag: str | None = None, *, project_root: Path = PROJECT_ROOT) -> str:
    pyproject = tomllib.loads((project_root / "pyproject.toml").read_text(encoding="utf-8"))
    package_version = pyproject.get("project", {}).get("version")
    init_text = (project_root / "src/codex_codeshark/__init__.py").read_text(
        encoding="utf-8"
    )
    match = re.search(r'^__version__\s*=\s*"([^"]+)"', init_text, re.MULTILINE)
    init_version = match.group(1) if match else None
    if not isinstance(package_version, str) or package_version != init_version:
        raise RuntimeError(
            f"version mismatch: pyproject={package_version!r}, package={init_version!r}"
        )
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", package_version):
        raise RuntimeError(f"version is not a stable semantic version: {package_version!r}")
    if tag is not None and tag != f"v{package_version}":
        raise RuntimeError(f"tag {tag!r} does not match version v{package_version}")
    missing = [name for name in REQUIRED_FILES if not (project_root / name).is_file()]
    if missing:
        raise RuntimeError("missing release files: " + ", ".join(missing))
    changelog = (project_root / "CHANGELOG.md").read_text(encoding="utf-8")
    if f"## {package_version} -" not in changelog:
        raise RuntimeError(f"CHANGELOG.md has no dated entry for {package_version}")
    return package_version


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a Codex-codeshark release")
    parser.add_argument("--tag", help="expected signed release tag, for example v0.1.0")
    args = parser.parse_args()
    try:
        version = check_release(args.tag)
    except (OSError, RuntimeError, tomllib.TOMLDecodeError) as exc:
        print(f"release check failed: {exc}", file=sys.stderr)
        return 1
    print(f"release check passed for {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
