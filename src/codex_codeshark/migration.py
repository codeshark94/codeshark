from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import stat
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .config import PROJECT_ROOT


ARCHIVE_FORMAT = "codex-codeshark-personal-data"
ARCHIVE_VERSION = 1
MAX_ARCHIVE_BYTES = 100_000_000
MAX_ARCHIVE_FILES = 500
_RUNTIME_FILES = ("memory.json", "feedback.jsonl", "feedback.jsonl.1")
_SKILL_PATH = re.compile(r"runtime/skills/(?:index\.json|s[0-9]+/SKILL\.md)")


class MigrationError(RuntimeError):
    pass


@dataclass(frozen=True)
class MigrationResult:
    archive: Path
    files: tuple[str, ...]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_allowed_archive_path(name: str) -> bool:
    if name in {f"runtime/{item}" for item in _RUNTIME_FILES}:
        return True
    if name == "runtime/agent.db":
        return True
    return bool(_SKILL_PATH.fullmatch(name))


def _sanitize_database(path: Path) -> None:
    try:
        with sqlite3.connect(path) as connection:
            result = connection.execute("PRAGMA quick_check").fetchone()
            if result is None or result[0] != "ok":
                raise MigrationError("personal-data database failed SQLite quick_check")
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
            required = {"tasks", "schedules", "learning_candidates"}
            if not required.issubset(tables):
                missing = ", ".join(sorted(required - tables))
                raise MigrationError(f"personal-data database is missing tables: {missing}")
            connection.execute(
                "UPDATE tasks SET status = 'cancelled', prompt = '', finished_at = ? "
                "WHERE status IN ('awaiting_approval', 'queued', 'running')",
                (datetime.now(timezone.utc).timestamp(),),
            )
            connection.execute(
                "UPDATE schedules SET status = 'paused' WHERE status = 'enabled'"
            )
            if "deliveries" in tables:
                connection.execute("DELETE FROM deliveries")
    except sqlite3.Error as exc:
        raise MigrationError(f"invalid personal-data database: {exc}") from exc


def _stage_personal_data(runtime_dir: Path, staging: Path) -> list[Path]:
    staged: list[Path] = []
    target_runtime = staging / "runtime"
    target_runtime.mkdir(parents=True)

    for filename in _RUNTIME_FILES:
        source = runtime_dir / filename
        if source.is_file():
            destination = target_runtime / filename
            shutil.copy2(source, destination)
            staged.append(destination)

    database = runtime_dir / "agent.db"
    if database.is_file():
        destination = target_runtime / "agent.db"
        try:
            with (
                sqlite3.connect(database) as source,
                sqlite3.connect(destination) as target,
            ):
                source.backup(target)
        except sqlite3.Error as exc:
            raise MigrationError(f"cannot snapshot personal-data database: {exc}") from exc
        _sanitize_database(destination)
        staged.append(destination)

    skills = runtime_dir / "skills"
    if skills.is_dir():
        for source in sorted(skills.rglob("*")):
            if not source.is_file() or source.is_symlink():
                continue
            relative = source.relative_to(runtime_dir)
            archive_name = "runtime/" + relative.as_posix()
            if not _is_allowed_archive_path(archive_name):
                continue
            destination = target_runtime / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            staged.append(destination)
    return staged


def export_personal_data(
    archive: Path,
    *,
    runtime_dir: Path | None = None,
    replace: bool = False,
) -> MigrationResult:
    destination = archive.expanduser().resolve()
    if destination.exists() and not replace:
        raise MigrationError(f"archive already exists: {destination}; use --force to replace it")
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_runtime = runtime_dir or PROJECT_ROOT / "runtime"

    with tempfile.TemporaryDirectory(prefix="codeshark-export-") as directory:
        staging = Path(directory)
        staged = _stage_personal_data(source_runtime, staging)
        if not staged:
            raise MigrationError("no personal data is available to export")
        files: dict[str, dict[str, int | str]] = {}
        for path in staged:
            name = path.relative_to(staging).as_posix()
            files[name] = {"size": path.stat().st_size, "sha256": _sha256(path)}
        manifest = {
            "format": ARCHIVE_FORMAT,
            "version": ARCHIVE_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "files": files,
            "excluded": [
                "Telegram bot token",
                "config.local.toml",
                "Codex session files",
                "runtime/state.json",
                "runtime logs",
                "failed Telegram deliveries",
                "workspace/inbox attachments",
            ],
        }
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        try:
            with zipfile.ZipFile(
                temporary,
                "w",
                compression=zipfile.ZIP_DEFLATED,
                compresslevel=6,
            ) as bundle:
                bundle.writestr(
                    "manifest.json",
                    json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                )
                for path in staged:
                    bundle.write(path, path.relative_to(staging).as_posix())
            temporary.chmod(0o600)
            os.replace(temporary, destination)
        finally:
            if temporary.exists():
                temporary.unlink()
    return MigrationResult(destination, tuple(sorted(files)))


def _read_and_validate_archive(archive: Path, staging: Path) -> tuple[str, ...]:
    try:
        bundle = zipfile.ZipFile(archive)
    except (OSError, zipfile.BadZipFile) as exc:
        raise MigrationError(f"cannot read migration archive: {exc}") from exc
    with bundle:
        infos = bundle.infolist()
        names = [info.filename for info in infos]
        if len(infos) > MAX_ARCHIVE_FILES or len(names) != len(set(names)):
            raise MigrationError("migration archive has too many or duplicate entries")
        if "manifest.json" not in names:
            raise MigrationError("migration archive is missing manifest.json")
        total_size = sum(info.file_size for info in infos)
        if total_size > MAX_ARCHIVE_BYTES:
            raise MigrationError("migration archive exceeds the 100 MB safety limit")
        for info in infos:
            mode = (info.external_attr >> 16) & 0o170000
            if stat.S_ISLNK(mode):
                raise MigrationError("migration archive must not contain symbolic links")
        try:
            manifest = json.loads(bundle.read("manifest.json"))
        except (KeyError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise MigrationError(f"invalid migration manifest: {exc}") from exc
        if not isinstance(manifest, dict):
            raise MigrationError("migration manifest must be a JSON object")
        if manifest.get("format") != ARCHIVE_FORMAT or manifest.get("version") != ARCHIVE_VERSION:
            raise MigrationError("unsupported migration archive format or version")
        files = manifest.get("files")
        if not isinstance(files, dict) or not files:
            raise MigrationError("migration manifest contains no personal-data files")
        if set(names) != {"manifest.json", *files.keys()}:
            raise MigrationError("migration archive entries do not match its manifest")

        for name, metadata in files.items():
            if not isinstance(name, str) or not _is_allowed_archive_path(name):
                raise MigrationError(f"migration archive contains an invalid path: {name}")
            if not isinstance(metadata, dict):
                raise MigrationError(f"invalid manifest metadata for {name}")
            try:
                data = bundle.read(name)
            except KeyError as exc:
                raise MigrationError(f"migration archive is missing {name}") from exc
            expected_size = metadata.get("size")
            expected_hash = metadata.get("sha256")
            actual_hash = hashlib.sha256(data).hexdigest()
            if expected_size != len(data) or expected_hash != actual_hash:
                raise MigrationError(f"migration archive checksum mismatch: {name}")
            destination = staging / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
    database = staging / "runtime" / "agent.db"
    if database.is_file():
        _sanitize_database(database)
    return tuple(sorted(files))


def _existing_personal_data(runtime_dir: Path) -> list[Path]:
    paths = [runtime_dir / filename for filename in _RUNTIME_FILES]
    paths.extend((runtime_dir / "agent.db", runtime_dir / "skills"))
    return [path for path in paths if path.exists()]


def _replace_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".import.tmp")
    shutil.copy2(source, temporary)
    temporary.chmod(0o600)
    os.replace(temporary, destination)


def import_personal_data(
    archive: Path,
    *,
    runtime_dir: Path | None = None,
    replace: bool = False,
) -> MigrationResult:
    source = archive.expanduser().resolve()
    if not source.is_file():
        raise MigrationError(f"migration archive does not exist: {source}")
    destination_runtime = runtime_dir or PROJECT_ROOT / "runtime"
    existing = _existing_personal_data(destination_runtime)
    if existing and not replace:
        names = ", ".join(path.name for path in existing)
        raise MigrationError(f"personal data already exists ({names}); use --force to replace it")

    with tempfile.TemporaryDirectory(prefix="codeshark-import-") as directory:
        staging = Path(directory)
        files = _read_and_validate_archive(source, staging)
        staged_runtime = staging / "runtime"
        destination_runtime.mkdir(parents=True, exist_ok=True)

        for filename in (*_RUNTIME_FILES, "agent.db"):
            destination = destination_runtime / filename
            staged = staged_runtime / filename
            if staged.is_file():
                _replace_file(staged, destination)
            elif replace and destination.exists():
                destination.unlink()

        staged_skills = staged_runtime / "skills"
        destination_skills = destination_runtime / "skills"
        if replace and destination_skills.exists():
            shutil.rmtree(destination_skills)
        if staged_skills.is_dir():
            shutil.copytree(staged_skills, destination_skills)
            destination_skills.chmod(0o700)
            for path in destination_skills.rglob("*"):
                path.chmod(0o700 if path.is_dir() else 0o600)
    return MigrationResult(source, files)
