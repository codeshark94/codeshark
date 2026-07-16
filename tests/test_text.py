import unittest

from codex_codeshark.app import split_message


class SplitMessageTests(unittest.TestCase):
    def test_keeps_short_message(self) -> None:
        self.assertEqual(split_message("hello", limit=10), ["hello"])

    def test_splits_without_losing_text(self) -> None:
        chunks = split_message("one two three four five", limit=10)
        self.assertTrue(all(len(chunk) <= 10 for chunk in chunks))
        self.assertEqual(" ".join(chunks), "one two three four five")


if __name__ == "__main__":
    unittest.main()
