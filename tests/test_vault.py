import tempfile
import unittest
from pathlib import Path

from codex_codeshark.vault import VaultStore


class VaultStoreTests(unittest.TestCase):
    def test_upserts_selects_and_forgets_structured_assets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = VaultStore(Path(directory) / "vault.json")
            project = store.upsert("project", "Codeshark", "Telegram is only the remote interface")
            decision = store.upsert("decision", "Memory sync", "Use a private vault, not Codex auth")
            updated = store.upsert("project", "codeshark", "Local persistent Codex agent")

            self.assertEqual(updated.id, project.id)
            selected = store.select("Codeshark local agent")
            self.assertEqual([item.id for item in selected], [project.id])
            self.assertTrue(store.forget(decision.id))
            self.assertFalse(store.forget("a99"))

    def test_rejects_unknown_asset_kind(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = VaultStore(Path(directory) / "vault.json")
            with self.assertRaisesRegex(ValueError, "asset kind"):
                store.upsert("credential", "Token", "do not store this")

    def test_scopes_assets_by_project(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = VaultStore(Path(directory) / "vault.json")
            research = store.upsert("project", "Plan", "Research plan", scope="Research")
            store.upsert("project", "Plan", "Trading plan", scope="Trading")

            self.assertEqual(
                [item.id for item in store.select("plan", scope="Research")],
                [research.id],
            )
