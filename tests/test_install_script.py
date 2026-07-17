import subprocess
import unittest
from pathlib import Path


class InstallScriptTests(unittest.TestCase):
    def test_installer_has_safe_interactive_protocol(self) -> None:
        script = Path(__file__).resolve().parents[1] / "scripts" / "install.sh"
        content = script.read_text(encoding="utf-8")

        self.assertIn("set -eu", content)
        self.assertIn('run_codeshark setup', content)
        self.assertIn('run_codeshark doctor', content)
        self.assertIn('run_codeshark start', content)
        self.assertIn("macOS Keychain", content)
        self.assertNotIn("TELEGRAM_BOT_TOKEN=", content)
        self.assertNotIn("git clone \"$REPOSITORY_URL\" \"$INSTALL_DIR\" |", content)
        result = subprocess.run(["/bin/sh", "-n", str(script)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
