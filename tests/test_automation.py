import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from codex_codeshark.automation import AgentStore, RiskPolicy, next_cron_time


class RiskPolicyTests(unittest.TestCase):
    def test_requires_approval_for_external_or_destructive_actions(self) -> None:
        policy = RiskPolicy()
        self.assertTrue(policy.requires_approval("deploy to production"))
        self.assertTrue(policy.requires_approval("send this email"))
        self.assertTrue(policy.requires_approval("delete the release"))
        self.assertFalse(policy.requires_approval("explain the code"))


class AgentStoreTests(unittest.TestCase):
    def test_persists_and_recovers_running_task(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "agent.db"
            store = AgentStore(path)
            task = store.enqueue_task(123, "do work", source="telegram", ephemeral=False)
            claimed = store.claim_next_task(now=task.created_at + 1)
            self.assertEqual(claimed.id, task.id)
            self.assertEqual(claimed.status, "running")

            restored = AgentStore(path)
            recovered = restored.claim_next_task(now=task.created_at + 2)
            self.assertEqual(recovered.id, task.id)

    def test_task_approval_and_prompt_purge_on_completion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = AgentStore(Path(directory) / "agent.db")
            task = store.enqueue_task(
                123,
                "deploy",
                source="telegram",
                ephemeral=False,
                requires_approval=True,
            )
            self.assertEqual(task.status, "awaiting_approval")
            self.assertIsNone(store.claim_next_task())
            self.assertTrue(store.approve(task.id))
            claimed = store.claim_next_task()
            self.assertTrue(claimed.approved)
            store.finish_task(claimed.id, "completed")
            completed = store.get_task(claimed.id)
            self.assertEqual(completed.prompt, "")
            self.assertEqual(completed.status, "completed")

    def test_due_reminder_enqueues_one_ephemeral_task(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = AgentStore(Path(directory) / "agent.db")
            schedule = store.create_schedule(
                123,
                kind="once",
                expression="",
                prompt="check server",
                next_run_at=100.0,
            )
            self.assertEqual(store.enqueue_due_schedules(now=99.0), 0)
            self.assertEqual(store.enqueue_due_schedules(now=100.0), 1)
            task = store.claim_next_task(now=100.0)
            self.assertTrue(task.ephemeral)
            self.assertEqual(task.source, "reminder")
            self.assertEqual(store.get_schedule(schedule.id).status, "completed")

    def test_schedule_approval_is_persistent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = AgentStore(Path(directory) / "agent.db")
            schedule = store.create_schedule(
                123,
                kind="interval",
                expression="300",
                prompt="deploy",
                next_run_at=100.0,
                requires_approval=True,
            )
            self.assertEqual(schedule.status, "awaiting_approval")
            self.assertTrue(store.approve(schedule.id, now=50.0))
            self.assertEqual(store.get_schedule(schedule.id).status, "enabled")
            self.assertTrue(store.get_schedule(schedule.id).approved)

    def test_interrupted_approved_task_requires_reapproval(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "agent.db"
            store = AgentStore(path)
            task = store.enqueue_task(
                123,
                "deploy",
                source="telegram",
                ephemeral=False,
                requires_approval=True,
            )
            store.approve(task.id)
            store.claim_next_task()

            recovered = AgentStore(path).get_task(task.id)
            self.assertEqual(recovered.status, "awaiting_approval")
            self.assertTrue(recovered.approved)

    def test_recurring_schedule_does_not_build_an_overlapping_backlog(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = AgentStore(Path(directory) / "agent.db")
            schedule = store.create_schedule(
                123,
                kind="heartbeat",
                expression="60",
                prompt="check server",
                next_run_at=100.0,
            )
            self.assertEqual(store.enqueue_due_schedules(now=100.0), 1)
            self.assertEqual(store.enqueue_due_schedules(now=200.0), 0)
            self.assertEqual(len(store.list_tasks()), 1)
            self.assertEqual(store.get_schedule(schedule.id).next_run_at, 260.0)

    def test_terminal_task_history_is_pruned_while_running(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = AgentStore(Path(directory) / "agent.db")
            for number in range(205):
                task = store.enqueue_task(
                    123,
                    f"task {number}",
                    source="telegram",
                    ephemeral=False,
                )
                claimed = store.claim_next_task(now=task.created_at + 1)
                store.finish_task(claimed.id, "completed")
            self.assertEqual(len(store.list_tasks(limit=1000)), 200)


class CronTests(unittest.TestCase):
    def test_next_cron_time_supports_steps_and_exact_values(self) -> None:
        start = datetime(2026, 7, 16, 10, 1, tzinfo=timezone.utc)
        result = next_cron_time("*/15 10 * * *", start)
        self.assertEqual(result, datetime(2026, 7, 16, 10, 15, tzinfo=timezone.utc))

    def test_rejects_invalid_cron(self) -> None:
        with self.assertRaises(ValueError):
            next_cron_time("bad cron", datetime.now(timezone.utc))


if __name__ == "__main__":
    unittest.main()
