import unittest

from codex_codeshark.identity import administrator_identity, restricted_group_identity


class IdentityTests(unittest.TestCase):
    def test_administrator_identity_describes_the_agent_without_its_transport(self) -> None:
        identity = administrator_identity("Codeshark", None, owner_onboarding_requested=False)

        self.assertIn("private local Codex agent", identity)
        self.assertNotIn("Telegram", identity)

    def test_group_identity_describes_the_agent_without_its_transport(self) -> None:
        identity = restricted_group_identity("Codeshark", None)

        self.assertIn("private local Codex agent", identity)
        self.assertNotIn("Telegram", identity)


if __name__ == "__main__":
    unittest.main()
