from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from .app import AgentApp
from .automation import AgentStore
from .config import (
    ConfigError,
    ORCHESTRATION_TIERS,
    OrchestrationProfile,
    PROJECT_ROOT,
    load_bot_token,
    load_config,
    set_model_assignments,
    set_orchestration,
    set_security_settings,
    set_workspace_directory,
    validate_codex_profile,
    validate_codex_version,
    validate_mcp_policy,
)
from .doctor import run_doctor
from .local_console import local_history, submit_local_request
from .migration import MigrationError, export_personal_data, import_personal_data
from .personal_sync import PersonalDataSync, PersonalSyncError
from .service import (
    ServiceError,
    read_logs,
    refresh_menu_bar,
    restart_service,
    restart_when_idle,
    service_status,
    start_service,
    stop_service,
    wait_for_deferred_restart,
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
    commands.add_parser("restart-when-idle", help=argparse.SUPPRESS)
    commands.add_parser("refresh-menu", help="rebuild and restart only the menu bar")
    commands.add_parser("apply-pending-restart", help=argparse.SUPPRESS)
    commands.add_parser("service-status", help="show the background service status")
    security = commands.add_parser("set-security", help="set Codeshark execution security settings")
    security.add_argument("--network", required=True, choices=("true", "false"))
    security.add_argument("--admin-full-access", required=True, choices=("true", "false"))
    security.add_argument("--admin-auto-approve-actions", required=True, choices=("true", "false"))
    security.add_argument("--admin-mcp-enabled", required=True, choices=("true", "false"))
    security.add_argument("--admin-delegated-write-access", required=True, choices=("true", "false"))
    security.add_argument("--group-auto-enable-on-admin-address", required=True, choices=("true", "false"))
    security.add_argument("--group-member-requests-enabled", required=True, choices=("true", "false"))
    security.add_argument("--group-auto-register-members", required=True, choices=("true", "false"))
    security.add_argument("--group-require-registered-members", required=True, choices=("true", "false"))
    security.add_argument("--group-respond-to-mentions", required=True, choices=("true", "false"))
    security.add_argument("--group-respond-to-bot-replies", required=True, choices=("true", "false"))
    security.add_argument("--group-respond-to-addressed-threads", required=True, choices=("true", "false"))
    security.add_argument("--group-network-access", required=True, choices=("true", "false"))
    security.add_argument("--group-workspace-write", required=True, choices=("true", "false"))
    local_history_parser = commands.add_parser("local-history", help=argparse.SUPPRESS)
    local_history_parser.add_argument("--limit", type=int, default=100)
    local_send = commands.add_parser("local-send", help=argparse.SUPPRESS)
    local_send.add_argument("--text", default="")
    local_send.add_argument("--file", action="append", type=Path, default=[])
    retry_task = commands.add_parser("retry-task", help=argparse.SUPPRESS)
    retry_task.add_argument("task_id")
    workspace = commands.add_parser("set-workspace", help="set the Codeshark workspace directory")
    workspace.add_argument("directory", type=Path)
    models = commands.add_parser("set-models", help="set the role-specific Codeshark models")
    models.add_argument("--routine", required=True)
    models.add_argument("--routine-effort", required=True)
    models.add_argument("--primary", required=True)
    models.add_argument("--primary-effort", required=True)
    models.add_argument("--rework", required=True)
    models.add_argument("--rework-effort", required=True)
    models.add_argument("--validator", required=True)
    models.add_argument("--validator-effort", required=True)
    models.add_argument("--feedback", required=True)
    models.add_argument("--feedback-effort", required=True)
    models.add_argument("--triage")
    models.add_argument("--triage-effort")
    models.add_argument("--preflight", required=True)
    models.add_argument("--preflight-effort", required=True)
    models.add_argument("--research")
    models.add_argument("--research-effort")
    models.add_argument("--finalizer")
    models.add_argument("--finalizer-effort")
    orchestration = commands.add_parser(
        "set-orchestration", help="set task-tier multi-agent orchestration"
    )
    for tier in ORCHESTRATION_TIERS:
        option = tier.replace("_", "-")
        orchestration.add_argument(f"--{option}-planning", required=True, choices=("true", "false"))
        orchestration.add_argument(f"--{option}-research", required=True, choices=("true", "false"))
        orchestration.add_argument(f"--{option}-validation", required=True, choices=("true", "false"))
        orchestration.add_argument(f"--{option}-feedback-loops", required=True, type=int)
        orchestration.add_argument(
            f"--{option}-adversarial-review", required=True, choices=("true", "false")
        )
        orchestration.add_argument(f"--{option}-finalization", required=True, choices=("true", "false"))
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
        if args.command == "refresh-menu":
            refresh_menu_bar()
            print("Menu bar: refreshed")
            return 0
        if args.command == "apply-pending-restart":
            status = wait_for_deferred_restart()
            if status is not None:
                print(f"Service: {status.state}")
                if status.pid is not None:
                    print(f"PID: {status.pid}")
            return 0
        if args.command == "restart-when-idle":
            status = restart_when_idle()
            if status is None:
                print("Restart: scheduled after active work finishes")
            else:
                print(f"Service: {status.state}")
                if status.pid is not None:
                    print(f"PID: {status.pid}")
            return 0
        if args.command == "set-security":
            config = set_security_settings(
                network_access=args.network == "true",
                admin_full_access=args.admin_full_access == "true",
                admin_auto_approve_actions=args.admin_auto_approve_actions == "true",
                admin_mcp_enabled=args.admin_mcp_enabled == "true",
                admin_delegated_write_access=args.admin_delegated_write_access == "true",
                group_auto_enable_on_admin_address=args.group_auto_enable_on_admin_address == "true",
                group_member_requests_enabled=args.group_member_requests_enabled == "true",
                group_auto_register_members=args.group_auto_register_members == "true",
                group_require_registered_members=args.group_require_registered_members == "true",
                group_respond_to_mentions=args.group_respond_to_mentions == "true",
                group_respond_to_bot_replies=args.group_respond_to_bot_replies == "true",
                group_respond_to_addressed_threads=args.group_respond_to_addressed_threads == "true",
                group_network_access=args.group_network_access == "true",
                group_workspace_write=args.group_workspace_write == "true",
            )
            status = restart_when_idle()
            print(
                "Security: "
                f"network={'enabled' if config.codex_network_access else 'disabled'}, "
                f"administrator={'full' if config.admin_full_access else 'workspace'}, "
                f"auto-approval={'enabled' if config.admin_auto_approve_actions else 'required'}, "
                f"MCP={'enabled' if config.admin_mcp_enabled else 'disabled'}, "
                f"group-auto-enable={'enabled' if config.group_auto_enable_on_admin_address else 'disabled'}, "
                f"group-requests={'enabled' if config.group_member_requests_enabled else 'disabled'}, "
                f"group-registration={'automatic' if config.group_auto_register_members else 'manual'}, "
                f"group-registered-only={'enabled' if config.group_require_registered_members else 'disabled'}, "
                f"group-network={'enabled' if config.group_network_access else 'disabled'}, "
                f"group-write={'enabled' if config.group_workspace_write else 'read-only'}"
            )
            if status is None:
                print("Restart: scheduled after active work finishes")
            return 0
        if args.command == "local-history":
            messages = local_history(load_config(), limit=args.limit)
            print(
                json.dumps(
                    {
                        "messages": [
                            {
                                "id": item.id,
                                "task_id": item.task_id,
                                "role": item.role,
                                "text": item.text,
                                "attachments": list(item.attachments),
                                "created_at": int(item.created_at),
                            }
                            for item in messages
                        ]
                    },
                    ensure_ascii=False,
                )
            )
            return 0
        if args.command == "local-send":
            submission = submit_local_request(
                load_config(),
                args.text,
                attachments=tuple(args.file),
            )
            print(
                json.dumps(
                    {
                        "task_id": submission.task_id,
                        "project": submission.project,
                        "attachments": [str(path) for path in submission.attachments],
                    },
                    ensure_ascii=False,
                )
            )
            return 0
        if args.command == "retry-task":
            config = load_config()
            store = AgentStore(config.state_path.parent / "agent.db")
            if store.pending_count() >= config.queue_size:
                raise ValueError("the task queue is full")
            task = store.retry_failed_task(args.task_id)
            if task is None:
                raise ValueError("this task is no longer eligible for a safe retry")
            print(json.dumps({"task_id": task.id}, ensure_ascii=False))
            return 0
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
            status = restart_when_idle()
            print(f"Workspace: {config.workdir}")
            if status is None:
                print("Restart: scheduled after active work finishes")
            return 0
        if args.command == "set-models":
            config = set_model_assignments(
                routine_model=args.routine,
                routine_reasoning_effort=args.routine_effort,
                primary_model=args.primary,
                primary_reasoning_effort=args.primary_effort,
                rework_model=args.rework,
                rework_reasoning_effort=args.rework_effort,
                validator_model=args.validator,
                validator_reasoning_effort=args.validator_effort,
                feedback_model=args.feedback,
                feedback_reasoning_effort=args.feedback_effort,
                triage_model=args.triage,
                triage_reasoning_effort=args.triage_effort,
                preflight_model=args.preflight,
                preflight_reasoning_effort=args.preflight_effort,
                research_model=args.research,
                research_reasoning_effort=args.research_effort,
                finalizer_model=args.finalizer,
                finalizer_reasoning_effort=args.finalizer_effort,
            )
            status = restart_when_idle()
            print(
                "Models: "
                f"routine={config.routine_model}, primary={config.primary_model}, "
                f"rework={config.rework_model}, validator={config.validator_model}, "
                f"feedback={config.feedback_model}, "
                f"triage={config.triage_model}, "
                f"preflight={config.preflight_model}, research={config.research_model}, "
                f"finalizer={config.finalizer_model}"
            )
            if status is None:
                print("Restart: scheduled after active work finishes")
            return 0
        if args.command == "set-orchestration":
            config = set_orchestration(
                profiles={
                    tier: OrchestrationProfile(
                        getattr(args, f"{tier}_planning") == "true",
                        getattr(args, f"{tier}_research") == "true",
                        getattr(args, f"{tier}_validation") == "true",
                        getattr(args, f"{tier}_feedback_loops"),
                        getattr(args, f"{tier}_finalization") == "true",
                        getattr(args, f"{tier}_adversarial_review") == "true",
                    )
                    for tier in ORCHESTRATION_TIERS
                }
            )
            status = restart_when_idle()
            print(
                "Orchestration updated: " + ", ".join(ORCHESTRATION_TIERS)
            )
            if status is None:
                print("Restart: scheduled after active work finishes")
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
