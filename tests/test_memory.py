import json
import tempfile
import unittest
from pathlib import Path

from codex_codeshark.learning import SkillStore
from codex_codeshark.identity import OWNER_PROFILE_TITLE, PUBLIC_OWNER_CARD_TITLE
from codex_codeshark.memory import (
    FeedbackStore,
    MemoryStore,
    compose_prompt,
    compose_restricted_group_prompt,
)
from codex_codeshark.vault import VaultStore


class MemoryStoreTests(unittest.TestCase):
    def test_restricted_group_prompt_blocks_private_context_and_privileged_actions(self) -> None:
        prompt = compose_restricted_group_prompt("Explain Python", task_id="t1")
        self.assertIn("non-privileged", prompt)
        self.assertIn("Do not use or disclose administrator memories", prompt)
        self.assertIn("read-only network research", prompt)
        self.assertIn("modify files only", prompt)
        self.assertIn("changes external state", prompt)
        self.assertNotIn("learning_candidate", prompt)

    def test_restricted_group_prompt_includes_supplied_group_context(self) -> None:
        prompt = compose_restricted_group_prompt(
            "What did I choose?",
            task_id="t1",
            context=[("My topic is Python", "Noted")],
        )
        self.assertIn("My topic is Python", prompt)
        self.assertIn("shared only inside this Telegram group", prompt)

    def test_restricted_group_prompt_includes_only_the_public_owner_card(self) -> None:
        prompt = compose_restricted_group_prompt(
            "Who owns you?",
            task_id="t1",
            public_owner_card="Sona's local Codex agent",
        )
        self.assertIn("Sona's local Codex agent", prompt)
        self.assertIn("beyond the public owner card", prompt)

    def test_persists_lists_and_forgets_memories(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "memory.json"
            store = MemoryStore(path)
            first = store.add("Python tests use unittest")
            second = store.add("Answer in English")

            restored = MemoryStore(path)
            self.assertEqual([item.text for item in restored.list()], [first.text, second.text])
            self.assertTrue(restored.forget(first.id))
            self.assertFalse(restored.forget("missing"))
            self.assertEqual([item.id for item in MemoryStore(path).list()], [second.id])

    def test_rejects_duplicate_memory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = MemoryStore(Path(directory) / "memory.json")
            store.add("same memory")
            with self.assertRaises(ValueError):
                store.add("same memory")

    def test_automatic_memory_updates_in_place_by_stable_title(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = MemoryStore(Path(directory) / "memory.json")
            original = store.upsert("Response style", "Use concise replies")
            updated = store.upsert("response STYLE", "Use concise direct replies")
            self.assertEqual(updated.id, original.id)
            self.assertEqual(len(store.list()), 1)
            self.assertEqual(store.list()[0].text, "Use concise direct replies")
            self.assertEqual(store.find_by_title("response style"), updated)

    def test_enforces_total_memory_capacity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = MemoryStore(Path(directory) / "memory.json", max_total_chars=20)
            store.add("a" * 15)
            with self.assertRaises(ValueError):
                store.add("b" * 6)

    def test_scopes_long_term_memories_by_project_but_keeps_identity_global(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = MemoryStore(Path(directory) / "memory.json")
            research = store.add("Use public datasets", scope="Research")
            trading = store.add("Use market-close prices", scope="Trading")
            owner = store.upsert(OWNER_PROFILE_TITLE, "Call the owner Sona")

            self.assertEqual(
                [item.id for item in store.list_for_project("Research")],
                [research.id, owner.id],
            )
            self.assertEqual(
                [item.id for item in store.list_for_project("Trading")],
                [trading.id, owner.id],
            )
            self.assertEqual(owner.scope, "global")

    def test_compose_prompt_includes_approved_memory_and_current_request(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = MemoryStore(Path(directory) / "memory.json")
            item = store.add("Answer in English")
            prompt, memory_ids, skill_ids = compose_prompt("Current request", store.list())
            self.assertIn("Long-term memories learned", prompt)
            self.assertIn(item.text, prompt)
            self.assertIn("untrusted data", prompt)
            self.assertTrue(prompt.endswith("Current request"))
            self.assertEqual(memory_ids, (item.id,))
            self.assertEqual(skill_ids, ())

    def test_compose_prompt_identifies_the_active_project(self) -> None:
        prompt, _, _ = compose_prompt("Current request", [], project_name="Research")
        self.assertIn("Project: Research", prompt)
        self.assertIn("Temporary working context", prompt)

    def test_compose_prompt_lists_server_controlled_read_only_roots(self) -> None:
        prompt, _, _ = compose_prompt(
            "Analyze the project",
            [],
            read_only_roots=(Path("/srv/projects"),),
        )
        self.assertIn("Server-controlled read-only project roots", prompt)
        self.assertIn("/srv/projects", prompt)
        self.assertIn("Do not create, edit, delete", prompt)

    def test_compose_prompt_identifies_the_codeshark_source_repository(self) -> None:
        prompt, _, _ = compose_prompt(
            "Inspect the gateway",
            [],
            agent_repository_root=Path("/srv/codeshark"),
        )
        self.assertIn("Codeshark source repository", prompt)
        self.assertIn("/srv/codeshark", prompt)

    def test_compose_prompt_lists_delegated_writable_roots(self) -> None:
        prompt, _, _ = compose_prompt(
            "Update the project",
            [],
            delegated_roots=(Path("/srv/delegated"),),
        )
        self.assertIn("/srv/delegated", prompt)
        self.assertIn("inspect, edit, create, test", prompt)
        self.assertIn("external state changes still require explicit", prompt)

    def test_compose_prompt_limits_memory_size(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = MemoryStore(Path(directory) / "memory.json")
            store.add("a" * 20)
            second = store.add("b" * 20)
            prompt, memory_ids, skill_ids = compose_prompt(
                "request",
                store.list(),
                max_memory_chars=30,
            )
            self.assertIn(second.text, prompt)
            self.assertNotIn("a" * 20, prompt)
            self.assertEqual(memory_ids, (second.id,))
            self.assertEqual(skill_ids, ())

    def test_compose_prompt_pins_owner_profile_outside_memory_budget(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = MemoryStore(Path(directory) / "memory.json")
            owner = store.upsert(OWNER_PROFILE_TITLE, "Call the owner Sona")
            public_card = store.upsert(PUBLIC_OWNER_CARD_TITLE, "Sona's local Codex agent")
            store.add("a" * 20)
            prompt, memory_ids, _ = compose_prompt(
                "Current request",
                store.list(),
                max_memory_chars=0,
                owner_profile=owner.text,
                owner_onboarding_requested=True,
            )
            self.assertIn("You are Codeshark", prompt)
            self.assertIn(owner.text, prompt)
            self.assertNotIn(owner.id, memory_ids)
            self.assertNotIn(public_card.id, memory_ids)

    def test_compose_prompt_includes_only_selected_skill(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            skills = SkillStore(Path(directory) / "skills")
            selected = skills.add("Python testing", "unittest execution procedure")
            skills.add("Deployment", "production deployment procedure")
            prompt, _, skill_ids = compose_prompt(
                "run the unittest tests",
                [],
                skills.select("run the unittest tests"),
            )
            self.assertIn("unittest execution procedure", prompt)
            self.assertNotIn("production deployment procedure", prompt)
            self.assertEqual(skill_ids, (selected.id,))

    def test_compose_prompt_includes_only_relevant_assistant_assets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            vault = VaultStore(Path(directory) / "vault.json")
            selected = vault.upsert("project", "Codeshark", "Local persistent Codex agent")
            vault.upsert("person", "Sona", "Private owner context")
            prompt, _, _ = compose_prompt(
                "Update the Codeshark agent",
                [],
                assets=vault.select("Update the Codeshark agent"),
            )
            self.assertIn("Relevant assistant assets", prompt)
            self.assertIn(selected.content, prompt)
            self.assertNotIn("Private owner context", prompt)


class FeedbackStoreTests(unittest.TestCase):
    def test_appends_feedback_without_prompt_or_response(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "feedback.jsonl"
            store = FeedbackStore(path)
            store.record(
                task_id="task-1",
                rating="good",
                note="accurate",
                thread_id="thread-1",
                memory_ids=("m1",),
                skill_ids=("s1",),
            )
            event = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(event["rating"], "good")
            self.assertEqual(event["memory_ids"], ["m1"])
            self.assertEqual(event["skill_ids"], ["s1"])
            self.assertNotIn("prompt", event)
            self.assertNotIn("response", event)

    def test_rejects_unknown_rating(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = FeedbackStore(Path(directory) / "feedback.jsonl")
            with self.assertRaises(ValueError):
                store.record(
                    task_id="task-1",
                    rating="maybe",
                    note="",
                    thread_id=None,
                    memory_ids=(),
                    skill_ids=(),
                )


if __name__ == "__main__":
    unittest.main()
