from __future__ import annotations

import argparse
import logging
from pathlib import Path

from .app import AgentApp
from .config import (
    ConfigError,
    load_bot_token,
    load_config,
    validate_codex_profile,
    validate_mcp_policy,
)
from .doctor import run_doctor
from .migration import MigrationError, export_personal_data, import_personal_data
from .setup_cli import interactive_setup
from .telegram_api import TelegramAPI


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="codex-codeshark")
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("run", help="Telegram gateway 실행")
    commands.add_parser("setup", help="Telegram과 Codex 로컬 설정")
    commands.add_parser("doctor", help="로컬 실행 환경 점검")
    for name, help_text in (
        ("export-data", "휴대 가능한 개인 데이터 내보내기"),
        ("import-data", "개인 데이터 가져오기"),
    ):
        migration = commands.add_parser(name, help=help_text)
        migration.add_argument("archive", type=Path)
        migration.add_argument(
            "--force",
            action="store_true",
            help="기존 archive 또는 개인 데이터를 교체",
        )
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
        if args.command == "export-data":
            result = export_personal_data(args.archive, replace=args.force)
            print(f"내보내기 완료: {result.archive} ({len(result.files)} files)")
            return 0
        if args.command == "import-data":
            result = import_personal_data(args.archive, replace=args.force)
            print(f"가져오기 완료: {result.archive} ({len(result.files)} files)")
            print("예약 작업은 일시정지 상태입니다. 확인 후 Telegram에서 재개하세요.")
            return 0
        config = load_config()
        validate_codex_profile(config)
        validate_mcp_policy(config)
        token = load_bot_token()
        AgentApp(config, TelegramAPI(token)).run_forever()
        return 0
    except (ConfigError, MigrationError, KeyboardInterrupt) as exc:
        if isinstance(exc, (ConfigError, MigrationError)):
            logging.error("%s", exc)
            return 1
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
