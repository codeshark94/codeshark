import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from codex_codeshark.setup_cli import interactive_setup


class SetupCliTests(unittest.TestCase):
    @patch("codex_codeshark.setup_cli.subprocess.run")
    def test_stops_before_secret_entry_when_codex_desktop_is_missing(self, run_mock) -> None:
        missing = Path("/missing/Codex.app/Contents/Resources/codex")
        output = io.StringIO()
        with patch("codex_codeshark.setup_cli.DEFAULT_CODEX_BINARY", missing), redirect_stdout(output):
            self.assertEqual(interactive_setup(), 1)

        run_mock.assert_not_called()
        self.assertIn("Codex desktop is not installed", output.getvalue())
