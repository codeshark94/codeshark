import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from codex_codeshark.config import (
    Config,
    ConfigError,
    configured_codex_runtime,
    validate_codex_profile,
    validate_codex_version,
    validate_bot_token,
    configured_mcp_servers,
    load_config,
    prompt_and_store_bot_token,
    prepare_group_runtime,
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
    def test_requires_codex_permission_profile_support(self, run_mock: Mock) -> None:
        run_mock.return_value = Mock(returncode=0, stdout="codex-cli 0.144.5", stderr="")
        self.assertEqual(validate_codex_version(Path("/codex")), "0.144.5")
        run_mock.return_value = Mock(returncode=0, stdout="codex-cli 0.137.0", stderr="")
        with self.assertRaisesRegex(ConfigError, "0.138.0"):
            validate_codex_version(Path("/codex"))

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
            read_only = root / "read-only"
            read_only.mkdir()
            delegated = root / "delegated"
            delegated.mkdir()
            config = root / "config.toml"
            config.write_text(
                "\n".join(
                    [
                        "allowed_user_ids = [123]",
                        f'workdir = "{workspace}"',
                        f'codex_binary = "{binary}"',
                        "max_session_turns = 25",
                        "admin_full_access = true",
                        f'read_only_roots = ["{read_only}"]',
                        f'delegated_roots = ["{delegated}"]',
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
            self.assertEqual(loaded.worker_count, 8)
            self.assertEqual(loaded.routine_model, "gpt-5.6-luna")
            self.assertEqual(loaded.routine_reasoning_effort, "medium")
            self.assertEqual(loaded.primary_model, "gpt-5.6-sol")
            self.assertEqual(loaded.primary_reasoning_effort, "high")
            self.assertEqual(loaded.validator_model, "gpt-5.6-terra")
            self.assertEqual(loaded.validator_reasoning_effort, "high")
            self.assertEqual(loaded.preflight_model, "gpt-5.6-luna")
            self.assertEqual(loaded.preflight_reasoning_effort, "low")
            self.assertFalse(loaded.codex_network_access)
            self.assertTrue(loaded.admin_full_access)
            self.assertEqual(loaded.attachment_max_bytes, 10_000_000)
            self.assertEqual(loaded.read_only_roots, (read_only.resolve(),))
            self.assertEqual(loaded.delegated_roots, (delegated.resolve(),))
            self.assertEqual(loaded.mcp_known_servers, ("github", "docs"))
            self.assertEqual(
                loaded.mcp_allowed_tools,
                (("github", ("list_issues", "get_issue")),),
            )

    def test_rejects_non_positive_worker_count(self) -> None:
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
                        "worker_count = 0",
                    ]
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ConfigError, "worker_count"):
                load_config(config)

    def test_rejects_reasoning_effort_above_high(self) -> None:
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
                        'primary_reasoning_effort = "xhigh"',
                    ]
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ConfigError, "primary_reasoning_effort"):
                load_config(config)

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

    def test_rejects_relative_read_only_root(self) -> None:
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
                        'read_only_roots = ["../other"]',
                    ]
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ConfigError, "absolute"):
                load_config(config)

    def test_rejects_overlapping_read_only_and_delegated_roots(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binary = root / "codex"
            binary.write_text("", encoding="utf-8")
            workspace = root / "workspace"
            workspace.mkdir()
            project = root / "projects"
            project.mkdir()
            delegated = project / "delegated"
            delegated.mkdir()
            config = root / "config.toml"
            config.write_text(
                "\n".join(
                    [
                        "allowed_user_ids = [123]",
                        f'workdir = "{workspace}"',
                        f'codex_binary = "{binary}"',
                        f'read_only_roots = ["{project}"]',
                        f'delegated_roots = ["{delegated}"]',
                    ]
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ConfigError, "cannot overlap"):
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

    def test_resolves_effective_model_from_global_and_profile_config(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config.toml").write_text(
                'model = "global-model"\nmodel_reasoning_effort = "high"\n',
                encoding="utf-8",
            )
            (root / "codex-codeshark.config.toml").write_text(
                'model = "profile-model"\n',
                encoding="utf-8",
            )
            self.assertEqual(
                configured_codex_runtime("codex-codeshark", codex_home=root),
                ("profile-model", "high"),
            )

    def test_prepares_group_runtime_with_auth_symlink_and_separate_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            codex_home = root / "admin-codex-home"
            codex_home.mkdir()
            auth = codex_home / "auth.json"
            auth.write_text("{}", encoding="utf-8")
            config = Config(
                allowed_user_ids=frozenset({123}),
                workdir=root,
                codex_binary=Path(__file__),
                codex_home=codex_home,
                group_workdir=root / "group" / "workspace",
                group_codex_home=root / "group" / "codex-home",
            )
            self.assertEqual(
                prepare_group_runtime(config),
                str((root / "group" / "workspace").resolve()),
            )
            link = config.group_codex_home / "auth.json"
            self.assertTrue(link.is_symlink())
            self.assertEqual(link.resolve(), auth.resolve())
            self.assertEqual(config.group_workdir.stat().st_mode & 0o777, 0o700)
            for worker_index in range(config.worker_count):
                self.assertTrue(
                    (config.group_codex_home / f"worker-{worker_index + 1}" / "auth.json").is_symlink()
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
            profile_text = path.read_text(encoding="utf-8")
            self.assertIn('service_tier = "standard"', profile_text)
            self.assertIn("fast_mode = false", profile_text)

            path.write_text(
                'sandbox_mode = "danger-full-access"\napproval_policy = "never"\n',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ConfigError, "workspace-write"):
                validate_codex_profile(config, codex_home=root)

    def test_existing_codex_profile_is_migrated_to_standard_without_losing_model(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "codex-codeshark.config.toml"
            path.write_text(
                'model = "gpt-5.6-sol"\nservice_tier = "priority"\n\n'
                "[features]\nfast_mode = true\n\n[sandbox_workspace_write]\n"
                "network_access = false\n",
                encoding="utf-8",
            )

            write_codex_profile("codex-codeshark", codex_home=root)

            profile_text = path.read_text(encoding="utf-8")
            self.assertIn('model = "gpt-5.6-sol"', profile_text)
            self.assertIn('service_tier = "standard"', profile_text)
            self.assertIn("[features]\nfast_mode = false", profile_text)
            self.assertIn("[sandbox_workspace_write]", profile_text)

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
            self.assertIn("read_only_roots = []", path.read_text(encoding="utf-8"))
            self.assertIn("delegated_roots = []", path.read_text(encoding="utf-8"))
            self.assertIn('routine_model = "gpt-5.6-luna"', path.read_text(encoding="utf-8"))
            self.assertIn('primary_model = "gpt-5.6-sol"', path.read_text(encoding="utf-8"))
            self.assertIn('validator_model = "gpt-5.6-terra"', path.read_text(encoding="utf-8"))
            self.assertIn(
                'preflight_reasoning_effort = "low"',
                path.read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    unittest.main()
