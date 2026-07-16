import io
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
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

    @patch("codex_codeshark.telegram_api.time.sleep")
    @patch("codex_codeshark.telegram_api.urllib.request.urlopen")
    def test_retries_rate_limit_with_retry_after(self, urlopen_mock: Mock, sleep_mock: Mock) -> None:
        error = urllib.error.HTTPError(
            "https://example.invalid",
            429,
            "rate limited",
            {},
            io.BytesIO(
                json.dumps(
                    {
                        "ok": False,
                        "description": "Too Many Requests",
                        "parameters": {"retry_after": 2},
                    }
                ).encode()
            ),
        )
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = b'{"ok":true,"result":{"id":1}}'
        urlopen_mock.side_effect = [error, response]

        api = TelegramAPI("123456789:ABC_def-123")
        self.assertEqual(api.get_me(), {"id": 1})
        sleep_mock.assert_called_once_with(2)
        self.assertEqual(urlopen_mock.call_count, 2)

    @patch("codex_codeshark.telegram_api.urllib.request.urlopen")
    def test_send_message_does_not_retry_ambiguous_connection_failure(
        self,
        urlopen_mock: Mock,
    ) -> None:
        urlopen_mock.side_effect = urllib.error.URLError("offline")
        api = TelegramAPI("123456789:ABC_def-123")
        with self.assertRaises(TelegramError) as caught:
            api.send_message(123, "final")
        self.assertTrue(caught.exception.ambiguous_delivery)
        self.assertEqual(urlopen_mock.call_count, 1)

    @patch("codex_codeshark.telegram_api.urllib.request.urlopen")
    def test_downloads_file_atomically_with_private_permissions(
        self,
        urlopen_mock: Mock,
    ) -> None:
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.headers = {"Content-Length": "4"}
        response.read.return_value = b"data"
        urlopen_mock.return_value = response
        api = TelegramAPI("123456789:ABC_def-123")
        api.get_file = Mock(return_value={"file_path": "documents/file.txt", "file_size": 4})
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "file.txt"
            self.assertEqual(api.download_file("file-1", destination, max_bytes=10), 4)
            self.assertEqual(destination.read_bytes(), b"data")
            self.assertEqual(destination.stat().st_mode & 0o777, 0o600)

    @patch("codex_codeshark.telegram_api.urllib.request.urlopen")
    def test_rejects_unsafe_download_path_without_requesting_it(
        self,
        urlopen_mock: Mock,
    ) -> None:
        api = TelegramAPI("123456789:ABC_def-123")
        api.get_file = Mock(return_value={"file_path": "../secret"})
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(TelegramError, "unsafe"):
                api.download_file("file-1", Path(directory) / "file", max_bytes=10)
        urlopen_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
