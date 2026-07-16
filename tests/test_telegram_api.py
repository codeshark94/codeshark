import json
import unittest
from unittest.mock import Mock, patch

from codex_codeshark.telegram_api import TelegramAPI, TelegramError, build_ssl_context


class TelegramAPITests(unittest.TestCase):
    def test_command_descriptions_are_english(self) -> None:
        api = TelegramAPI("123456789:ABC_def-123")
        api.call = Mock()
        api.set_commands()
        payload = api.call.call_args.args[1]
        commands = json.loads(payload["commands"])
        self.assertTrue(commands)
        for command in commands:
            self.assertNotRegex(command["description"], r"[가-힣]")

    @patch("codex_codeshark.telegram_api.Path.is_file", return_value=True)
    @patch("codex_codeshark.telegram_api.ssl.create_default_context")
    @patch("codex_codeshark.telegram_api.ssl.get_default_verify_paths")
    def test_uses_system_ca_when_python_has_no_default_ca(
        self,
        paths_mock: Mock,
        context_mock: Mock,
        _is_file_mock: Mock,
    ) -> None:
        paths_mock.return_value = Mock(cafile=None, capath=None)
        expected = Mock()
        context_mock.return_value = expected

        self.assertIs(build_ssl_context(), expected)
        context_mock.assert_called_once_with(cafile="/etc/ssl/cert.pem")

    def test_rejects_invalid_token_before_building_a_url(self) -> None:
        invalid = 'cd "$HOME/workspace/Codex-codeshark"'
        with self.assertRaises(TelegramError) as caught:
            TelegramAPI(invalid)
        self.assertNotIn(invalid, str(caught.exception))


if __name__ == "__main__":
    unittest.main()
