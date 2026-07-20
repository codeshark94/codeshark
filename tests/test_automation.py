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
        self.assertTrue(policy.requires_approval("erase every tracked file"))
        self.assertTrue(policy.requires_approval("alter the branch protection settings"))
        self.assertTrue(policy.requires_approval("fix the failing test"))
        self.assertTrue(policy.requires_approval("이 코드 수정해"))
        self.assertFalse(policy.requires_approval("explain the code"))

    def test_group_privilege_gate_allows_analysis_but_blocks_privileged_work(self) -> None:
        policy = RiskPolicy()
        self.assertFalse(
            policy.requires_group_admin_privileges(
                "research Python releases and write a summary to report.md"
            )
        )
        self.assertTrue(policy.requires_group_admin_privileges("delete every file"))
        self.assertTrue(policy.requires_group_admin_privileges("install a Python dependency"))
        self.assertTrue(policy.requires_group_admin_privileges("read the API key"))
        self.assertTrue(policy.requires_group_admin_privileges("create a GitHub issue"))
        self.assertTrue(policy.requires_group_admin_privileges("deploy to production"))


class AgentStoreTests(unittest.TestCase):
    def test_latest_failure_hides_after_a_later_successful_task(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = AgentStore(Path(directory) / "agent.db")
            failed = store.enqueue_task(123, "first", source="telegram", ephemeral=False)
            failed = store.claim_next_task(now=failed.created_at + 1)
            store.finish_task(failed.id, "failed", "first diagnostic")
            self.assertEqual(store.latest_failure().task_id, failed.id)

            completed = store.enqueue_task(456, "second", source="telegram", ephemeral=False)
            completed = store.claim_next_task(now=completed.created_at + 2)
            store.finish_task(completed.id, "completed")

            self.assertIsNone(store.latest_failure())

    def test_summarizes_model_runs_in_a_requested_time_window(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = AgentStore(Path(directory) / "agent.db")
            store.record_model_run(
                task_id="task-1",
                phase="primary",
                role="Primary",
                model="gpt-5.6-sol",
                reasoning_effort="high",
                started_at=100.0,
                finished_at=160.0,
                exit_code=0,
                cancelled=False,
                timed_out=False,
                input_tokens=120,
                cached_input_tokens=30,
                cache_write_input_tokens=10,
                output_tokens=40,
                reasoning_output_tokens=15,
                total_tokens=160,
                token_usage_recorded=True,
            )
            store.record_model_run(
                task_id="task-2",
                phase="validator",
                role="Validation",
                model="gpt-5.6-terra",
                reasoning_effort="high",
                started_at=200.0,
                finished_at=230.0,
                exit_code=1,
                cancelled=False,
                timed_out=False,
            )

            summaries = store.model_run_summaries(since=150.0)

            self.assertEqual(len(summaries), 2)
            self.assertEqual(summaries[0].model, "gpt-5.6-sol")
            self.assertEqual(summaries[0].runs, 1)
            self.assertEqual(summaries[0].completed, 1)
            self.assertEqual(summaries[0].elapsed_seconds, 60.0)
            self.assertEqual(summaries[0].measured_runs, 1)
            self.assertEqual(summaries[0].total_tokens, 160)
            self.assertEqual(summaries[1].model, "gpt-5.6-terra")
            self.assertEqual(summaries[1].completed, 0)
            self.assertEqual(summaries[1].measured_runs, 0)

            role_usage = store.model_role_usage(since=150.0)
            self.assertEqual(role_usage[0].role, "Primary")
            self.assertEqual(role_usage[0].total_tokens, 160)
            self.assertEqual(role_usage[1].role, "Validation")

    def test_summarizes_model_usage_by_project(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = AgentStore(Path(directory) / "agent.db")
            store.upsert_task_manifest(
                "task-1",
                project="Research",
                tier="deep",
                phase="completed",
            )
            store.record_model_run(
                task_id="task-1",
                phase="primary",
                role="Primary",
                model="gpt-5.6-luna",
                reasoning_effort="medium",
                started_at=100.0,
                finished_at=160.0,
                exit_code=0,
                cancelled=False,
                timed_out=False,
                input_tokens=120,
                cached_input_tokens=30,
                output_tokens=40,
                reasoning_output_tokens=15,
                total_tokens=160,
                token_usage_recorded=True,
            )

            usage = store.project_model_usage(since=150.0)

            self.assertEqual(len(usage), 1)
            self.assertEqual(usage[0].project, "Research")
            self.assertEqual(usage[0].model, "gpt-5.6-luna")
            self.assertEqual(usage[0].measured_runs, 1)
            self.assertEqual(usage[0].cached_input_tokens, 30)
            self.assertEqual(usage[0].reasoning_output_tokens, 15)

    def test_persists_and_recovers_running_task(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "agent.db"
            store = AgentStore(path)
            task = store.enqueue_task(123, "do work", source="telegram", ephemeral=False)
            claimed = store.claim_next_task(now=task.created_at + 1)
            self.assertEqual(claimed.id, task.id)
            self.assertEqual(claimed.status, "running")
            self.assertEqual(store.running_count(), 1)

            restored = AgentStore(path)
            self.assertEqual(restored.get_task(task.id).status, "running")
            self.assertEqual(restored.running_count(), 1)
            restored.recover_interrupted_tasks()
            self.assertEqual(restored.running_count(), 0)
            recovered = restored.claim_next_task(now=task.created_at + 2)
            self.assertEqual(recovered.id, task.id)

    def test_stale_attempt_cannot_finish_a_recovered_task(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = AgentStore(Path(directory) / "agent.db")
            task = store.enqueue_task(123, "do work", source="telegram", ephemeral=False)
            first = store.claim_next_task(now=task.created_at + 1)
            store.recover_interrupted_tasks()
            second = store.claim_next_task(now=task.created_at + 2)

            self.assertFalse(
                store.finish_task(first.id, "cancelled", attempt=first.attempts)
            )
            self.assertTrue(
                store.finish_task(second.id, "completed", attempt=second.attempts)
            )
            self.assertEqual(store.get_task(task.id).status, "completed")

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

    def test_claims_independent_tasks_in_parallel_without_racing_a_chat_session(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = AgentStore(Path(directory) / "agent.db")
            first = store.enqueue_task(123, "first", source="telegram", ephemeral=False)
            same_chat = store.enqueue_task(123, "second", source="telegram", ephemeral=False)
            other_chat = store.enqueue_task(456, "third", source="telegram", ephemeral=False)

            claimed_first = store.claim_next_task(now=other_chat.created_at + 1)
            claimed_other = store.claim_next_task(now=other_chat.created_at + 1)
            self.assertEqual(claimed_first.id, first.id)
            self.assertEqual(claimed_other.id, other_chat.id)
            self.assertIsNone(store.claim_next_task(now=other_chat.created_at + 1))

            store.finish_task(claimed_first.id, "completed")
            self.assertEqual(
                store.claim_next_task(now=other_chat.created_at + 2).id,
                same_chat.id,
            )

    def test_claims_restricted_group_requests_for_different_members_in_parallel(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = AgentStore(Path(directory) / "agent.db")
            first = store.enqueue_task(
                -100123,
                "first",
                source="telegram-group",
                ephemeral=True,
                restricted=True,
                requester_id=456,
            )
            second = store.enqueue_task(
                -100123,
                "second",
                source="telegram-group",
                ephemeral=True,
                restricted=True,
                requester_id=789,
            )
            third = store.enqueue_task(
                -100123,
                "third",
                source="telegram-group",
                ephemeral=True,
                restricted=True,
                requester_id=456,
            )

            claimed_first = store.claim_next_task(now=third.created_at + 1)
            claimed_second = store.claim_next_task(now=third.created_at + 1)
            self.assertEqual({claimed_first.id, claimed_second.id}, {first.id, second.id})
            self.assertIsNone(store.claim_next_task(now=third.created_at + 1))

            store.finish_task(claimed_first.id, "completed")
            self.assertEqual(
                store.claim_next_task(now=third.created_at + 2).id,
                third.id,
            )

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

            restored = AgentStore(path)
            restored.recover_interrupted_tasks()
            recovered = restored.get_task(task.id)
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

    def test_failed_delivery_can_be_retried_and_payload_is_purged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = AgentStore(Path(directory) / "agent.db")
            delivery = store.record_delivery_failure(123, "final result", "offline")
            self.assertEqual(store.list_failed_deliveries(), [delivery])
            self.assertTrue(store.mark_delivery_attempt(delivery.id, "still offline"))
            self.assertEqual(store.get_delivery(delivery.id).attempts, 2)
            self.assertTrue(store.mark_delivery_sent(delivery.id))
            sent = store.get_delivery(delivery.id)
            self.assertEqual(sent.status, "sent")
            self.assertEqual(sent.text, "")
            self.assertEqual(store.list_failed_deliveries(), [])

    def test_restricted_group_task_and_group_acl_are_persistent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "agent.db"
            store = AgentStore(path)
            group = store.enable_group(-100123, "Engineering", 123)
            self.assertEqual(group.chat_id, -100123)
            self.assertTrue(store.is_group_enabled(-100123))

            task = store.enqueue_task(
                -100123,
                "explain this",
                source="telegram-group",
                ephemeral=True,
                restricted=True,
                requester_id=456,
            )
            self.assertTrue(task.restricted)
            self.assertEqual(task.requester_id, 456)
            self.assertEqual(store.restricted_pending_count(), 1)

            restored = AgentStore(path)
            self.assertTrue(restored.is_group_enabled(-100123))
            self.assertTrue(restored.get_task(task.id).restricted)
            self.assertTrue(restored.disable_group(-100123))
            self.assertEqual(restored.list_groups(), [])
            cancelled = restored.get_task(task.id)
            self.assertEqual(cancelled.status, "cancelled")
            self.assertEqual(cancelled.prompt, "")
            self.assertEqual(restored.restricted_pending_count(), 0)

    def test_group_context_is_requester_scoped_bounded_and_deleted_with_group(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = AgentStore(Path(directory) / "agent.db")
            store.enable_group(-100123, "Engineering", 123)
            for number in range(7):
                store.append_group_context(
                    -100123,
                    456,
                    f"request {number}",
                    f"response {number}",
                    now=1000 + number,
                )
            context = store.group_context(-100123, 456, now=1007)
            self.assertEqual(len(context), 6)
            self.assertEqual(context[0][0], "request 1")
            self.assertEqual(store.group_context(-100123, 789, now=1007), [])
            self.assertTrue(store.disable_group(-100123))
            self.assertEqual(store.group_context(-100123, 456, now=1007), [])

    def test_group_addressed_messages_are_bounded_and_deleted_with_group(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = AgentStore(Path(directory) / "agent.db")
            store.enable_group(-100123, "Engineering", 123)

            store.remember_group_addressed_message(-100123, 10, now=1000)
            self.assertTrue(store.is_group_addressed_message(-100123, 10, now=1001))
            self.assertFalse(store.is_group_addressed_message(-100123, 10, now=1000 + 31 * 86400))

            store.remember_group_addressed_message(-100123, 11, now=1002)
            self.assertTrue(store.disable_group(-100123))
            self.assertFalse(store.is_group_addressed_message(-100123, 11, now=1003))


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
