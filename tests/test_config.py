import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from codex_codeshark.config import (
    Config,
    ConfigError,
    validate_codex_profile,
    validate_bot_token,
    configured_mcp_servers,
    load_config,
    prompt_and_store_bot_token,
    validate_mcp_policy,
    write_codex_profile,
    write_local_config,
)


class ConfigTests(unittest.TestCase):
    def test_validates_bot_token_without_echoing_invalid_value(self) -> None:
        token = "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZ_123456"
        self.assertEqual(validate_bot_token(f"  {token}\n"), token)
        invalid = 'cd "$HOME/workspace/Codex-codeshark"'
        with self.assertRaises(ConfigError) as caught:
            validate_bot_token(invalid)
        self.assertNotIn(invalid, str(caught.exception))

    @patch("codex_codeshark.config.subprocess.run")
    @patch("codex_codeshark.config.getpass.getpass")
    def test_stores_validated_token_without_command_line_exposure(
        self,
        getpass_mock: Mock,
        run_mock: Mock,
    ) -> None:
        token = "123456789:ABC_def-123"
        getpass_mock.return_value = token
        run_mock.return_value = Mock(returncode=0)

        self.assertEqual(prompt_and_store_bot_token(), token)
        command = run_mock.call_args.args[0]
        self.assertNotIn(token, command)
        self.assertEqual(run_mock.call_args.kwargs["input"], f"{token}\n{token}\n")
        self.assertTrue(run_mock.call_args.kwargs["capture_output"])

    def test_loads_valid_config(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binary = root / "codex"
            binary.write_text("", encoding="utf-8")
            workspace = root / "workspace"
            workspace.mkdir()
            config = root / "config.toml"
            config.write_text(
                "\n".join(
                    [
                        "allowed_user_ids = [123]",
                        f'workdir = "{workspace}"',
                        f'codex_binary = "{binary}"',
                        "max_session_turns = 25",
                        '[mcp_policy]',
                        'known_servers = ["github", "docs"]',
                        '[mcp_policy.allowed_tools]',
                        'github = ["list_issues", "get_issue"]',
                    ]
                ),
                encoding="utf-8",
            )
            loaded = load_config(config)
            self.assertEqual(loaded.allowed_user_ids, frozenset({123}))
            self.assertEqual(loaded.workdir, workspace.resolve())
            self.assertEqual(loaded.max_session_turns, 25)
            self.assertFalse(loaded.codex_network_access)
            self.assertEqual(loaded.attachment_max_bytes, 10_000_000)
            self.assertEqual(loaded.mcp_known_servers, ("github", "docs"))
            self.assertEqual(
                loaded.mcp_allowed_tools,
                (("github", ("list_issues", "get_issue")),),
            )

    def test_rejects_empty_allowlist(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.toml"
            config.write_text("allowed_user_ids = []\n", encoding="utf-8")
            with self.assertRaises(ConfigError):
                load_config(config)

    def test_rejects_multiple_users_sharing_one_session(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.toml"
            config.write_text("allowed_user_ids = [1, 2]\n", encoding="utf-8")
            with self.assertRaises(ConfigError):
                load_config(config)

    def test_rejects_non_boolean_network_policy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binary = root / "codex"
            binary.write_text("", encoding="utf-8")
            workspace = root / "workspace"
            workspace.mkdir()
            config = root / "config.toml"
            config.write_text(
                "\n".join(
                    [
                        "allowed_user_ids = [123]",
                        f'workdir = "{workspace}"',
                        f'codex_binary = "{binary}"',
                        'codex_network_access = "yes"',
                    ]
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ConfigError, "true or false"):
                load_config(config)

    def test_rejects_mcp_allowlist_server_not_in_known_servers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binary = root / "codex"
            binary.write_text("", encoding="utf-8")
            workspace = root / "workspace"
            workspace.mkdir()
            config = root / "config.toml"
            config.write_text(
                "\n".join(
                    [
                        "allowed_user_ids = [123]",
                        f'workdir = "{workspace}"',
                        f'codex_binary = "{binary}"',
                        '[mcp_policy]',
                        'known_servers = ["docs"]',
                        '[mcp_policy.allowed_tools]',
                        'github = ["list_issues"]',
                    ]
                ),
                encoding="utf-8",
            )
            with self.assertRaises(ConfigError):
                load_config(config)

    def test_mcp_policy_must_cover_global_and_profile_servers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            codex_home = root / ".codex"
            codex_home.mkdir()
            (codex_home / "config.toml").write_text(
                '[mcp_servers.docs]\ncommand = "docs"\n',
                encoding="utf-8",
            )
            (codex_home / "codex-codeshark.config.toml").write_text(
                '[mcp_servers.github]\ncommand = "github"\n',
                encoding="utf-8",
            )
            config = Config(
                allowed_user_ids=frozenset({123}),
                workdir=root,
                codex_binary=Path(__file__),
                mcp_known_servers=("docs",),
                mcp_allowed_tools=(("docs", ("search",)),),
            )
            self.assertEqual(
                configured_mcp_servers(config.codex_profile, codex_home=codex_home),
                frozenset({"docs", "github"}),
            )
            with self.assertRaisesRegex(ConfigError, "github"):
                validate_mcp_policy(config, codex_home=codex_home)

            covered = Config(
                allowed_user_ids=config.allowed_user_ids,
                workdir=config.workdir,
                codex_binary=config.codex_binary,
                mcp_known_servers=("docs", "github"),
                mcp_allowed_tools=(("docs", ("search",)),),
            )
            self.assertEqual(
                validate_mcp_policy(covered, codex_home=codex_home),
                "2 configured, 1 allowed",
            )

    def test_writes_and_validates_restricted_codex_profile(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = write_codex_profile("codex-codeshark", codex_home=root)
            config = Config(
                allowed_user_ids=frozenset({123}),
                workdir=root,
                codex_binary=Path(__file__),
            )
            self.assertEqual(validate_codex_profile(config, codex_home=root), "codex-codeshark")

            path.write_text(
                'sandbox_mode = "danger-full-access"\napproval_policy = "never"\n',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ConfigError, "workspace-write"):
                validate_codex_profile(config, codex_home=root)

    def test_generated_config_registers_existing_mcp_servers_as_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            codex_home = root / ".codex"
            codex_home.mkdir()
            (codex_home / "config.toml").write_text(
                '[mcp_servers.docs]\ncommand = "docs"\n',
                encoding="utf-8",
            )
            path = write_local_config(
                123,
                root / "config.toml",
                codex_home=codex_home,
                project_root=root,
            )
            self.assertIn('known_servers = ["docs"]', path.read_text(encoding="utf-8"))
            self.assertTrue((root / "workspace").is_dir())
            self.assertEqual((root / "workspace").stat().st_mode & 0o777, 0o700)


if __name__ == "__main__":
    unittest.main()
