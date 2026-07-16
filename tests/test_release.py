import importlib.util
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "release_check",
    PROJECT_ROOT / "scripts/release_check.py",
)
release_check = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(release_check)


class ReleaseCheckTests(unittest.TestCase):
    def test_current_source_tree_is_release_consistent(self) -> None:
        self.assertEqual(
            release_check.check_release("v0.1.0", project_root=PROJECT_ROOT),
            "0.1.0",
        )

    def test_tag_must_match_package_version(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "does not match"):
            release_check.check_release("v9.9.9", project_root=PROJECT_ROOT)


if __name__ == "__main__":
    unittest.main()
