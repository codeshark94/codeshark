from __future__ import annotations

import argparse
import logging
from pathlib import Path

from .app import AgentApp
from .config import (
    ConfigError,
    PROJECT_ROOT,
    load_bot_token,
    load_config,
    set_model_assignments,
    set_workspace_directory,
    validate_codex_profile,
    validate_codex_version,
    validate_mcp_policy,
)
from .doctor import run_doctor
from .migration import MigrationError, export_personal_data, import_personal_data
from .personal_sync import PersonalDataSync, PersonalSyncError
from .service import (
    ServiceError,
    read_logs,
    restart_service,
    service_status,
    start_service,
    stop_service,
)
from .setup_cli import interactive_setup
from .telegram_api import TelegramAPI, TelegramError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="codex-codeshark")
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("run", help="run the Telegram gateway")
    commands.add_parser("setup", help="configure Telegram and Codex locally")
    commands.add_parser("doctor", help="check the local runtime environment")
    commands.add_parser("start", help="start or install the background service")
    commands.add_parser("stop", help="stop the background service")
    commands.add_parser("restart", help="restart the background service")
    commands.add_parser("service-status", help="show the background service status")
    workspace = commands.add_parser("set-workspace", help="set the Codeshark workspace directory")
    workspace.add_argument("directory", type=Path)
    models = commands.add_parser("set-models", help="set the role-specific Codeshark models")
    models.add_argument("--routine", required=True)
    models.add_argument("--primary", required=True)
    models.add_argument("--validator", required=True)
    models.add_argument("--preflight", required=True)
    logs = commands.add_parser("logs", help="show sanitized background service logs")
    logs.add_argument("--lines", type=int, default=100)
    for name, help_text in (
        ("export-data", "export portable personal data"),
        ("import-data", "import personal data"),
    ):
        migration = commands.add_parser(name, help=help_text)
        migration.add_argument("archive", type=Path)
        migration.add_argument(
            "--force",
            action="store_true",
            help="replace an existing archive or local personal data",
        )
    sync = commands.add_parser("sync-data", help="configure private personal-data sync")
    sync_commands = sync.add_subparsers(dest="sync_command", required=True)
    enable = sync_commands.add_parser("enable", help="set a private sync directory")
    enable.add_argument("directory", type=Path)
    sync_commands.add_parser("status", help="show personal-data sync status")
    sync_commands.add_parser("push", help="write a current private archive to the sync directory")
    pull = sync_commands.add_parser("pull", help="replace local personal data from the sync directory")
    pull.add_argument("--force", action="store_true", help="replace existing local personal data")
    sync_commands.add_parser("disable", help="disable automatic personal-data backup")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        if args.command is None:
            args.command = "run"
        if args.command == "setup":
            return interactive_setup()
        if args.command == "doctor":
            return run_doctor()
        if args.command in {"start", "stop", "restart", "service-status"}:
            if args.command == "start":
                status = start_service()
            elif args.command == "stop":
                status = stop_service()
            elif args.command == "restart":
                status = restart_service()
            else:
                status = service_status()
            print(f"Service: {status.state}")
            if status.pid is not None:
                print(f"PID: {status.pid}")
            elif status.detail:
                print(status.detail)
            return 0 if status.running or args.command == "stop" else 1
        if args.command == "logs":
            print(read_logs(args.lines))
            return 0
        if args.command == "set-workspace":
            config = set_workspace_directory(args.directory)
            status = restart_service()
            if not status.running:
                raise ServiceError(status.detail or "service did not restart")
            print(f"Workspace: {config.workdir}")
            return 0
        if args.command == "set-models":
            config = set_model_assignments(
                routine_model=args.routine,
                primary_model=args.primary,
                validator_model=args.validator,
                preflight_model=args.preflight,
            )
            status = restart_service()
            if not status.running:
                raise ServiceError(status.detail or "service did not restart")
            print(
                "Models: "
                f"routine={config.routine_model}, primary={config.primary_model}, "
                f"validator={config.validator_model}, preflight={config.preflight_model}"
            )
            return 0
        if args.command == "export-data":
            result = export_personal_data(args.archive, replace=args.force)
            print(f"Export complete: {result.archive} ({len(result.files)} files)")
            return 0
        if args.command == "import-data":
            result = import_personal_data(args.archive, replace=args.force)
            print(f"Import complete: {result.archive} ({len(result.files)} files)")
            print("Scheduled jobs were imported as paused. Review and resume them in Telegram.")
            return 0
        if args.command == "sync-data":
            sync = PersonalDataSync(PROJECT_ROOT / "runtime")
            if args.sync_command == "enable":
                status = sync.configure(args.directory)
                print(f"Personal sync directory configured: {status.directory}")
                print("Run `sync-data push` on this Mac, or `sync-data pull --force` on a new Mac.")
                return 0
            if args.sync_command == "status":
                status = sync.status()
                if status.directory is None:
                    print("Personal sync: disabled")
                else:
                    mode = "automatic backup enabled" if status.automatic else "configured; initial push or pull required"
                    print(f"Personal sync: {mode}\nDirectory: {status.directory}")
                return 0
            if args.sync_command == "disable":
                sync.disable()
                print("Personal sync disabled.")
                return 0
            if args.sync_command == "pull" and service_status().running:
                raise PersonalSyncError("stop the background service before replacing personal data")
            result = sync.pull(replace=args.force) if args.sync_command == "pull" else sync.push()
            print(f"Personal sync {args.sync_command} complete: {result.archive} ({len(result.files)} files)")
            return 0
        config = load_config()
        validate_codex_version(config.codex_binary)
        validate_codex_profile(config)
        validate_mcp_policy(config)
        token = load_bot_token()
        AgentApp(config, TelegramAPI(token)).run_forever()
        return 0
    except (ConfigError, MigrationError, PersonalSyncError, ServiceError, TelegramError, KeyboardInterrupt) as exc:
        if isinstance(exc, (ConfigError, MigrationError, PersonalSyncError, ServiceError, TelegramError)):
            logging.error("%s", exc)
            return 1
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
