import json
import tempfile
import unittest
from pathlib import Path

from codex_codeshark.app import HELP_TEXT, AgentApp
from codex_codeshark.codex_runner import RunResult
from codex_codeshark.config import Config
from codex_codeshark.telegram_api import TelegramError


class FakeTelegramAPI:
    def __init__(self) -> None:
        self.messages = []

    def send_message(self, chat_id, text) -> None:
        self.messages.append((chat_id, text))

    def download_file(self, file_id, destination, *, max_bytes) -> int:
        destination.write_bytes(b"attachment")
        return 10


class FakeCodexRunner:
    def __init__(self, result: RunResult | None = None) -> None:
        self.model = "test-model"
        self.prompts = []
        self.deleted_sessions = []
        self.delete_error = None
        self.results = [
            result
            or RunResult(
                exit_code=0,
                message="done",
                thread_id="thread-new",
                stderr="",
            )
        ]

    def run(self, prompt, thread_id, *, ephemeral=False, restricted=False) -> RunResult:
        self.prompts.append((prompt, thread_id, ephemeral, restricted))
        if len(self.results) > 1:
            return self.results.pop(0)
        return self.results[0]

    def cancel(self) -> bool:
        return False

    def delete_session(self, thread_id) -> None:
        if self.delete_error:
            raise self.delete_error
        self.deleted_sessions.append(thread_id)


class AgentAppAuthorizationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        binary = root / "codex"
        binary.write_text("", encoding="utf-8")
        workspace = root / "workspace"
        workspace.mkdir()
        codex_home = root / "codex-home"
        codex_home.mkdir()
        (codex_home / "auth.json").write_text("{}", encoding="utf-8")
        config = Config(
            allowed_user_ids=frozenset({123}),
            workdir=workspace,
            codex_binary=binary,
            state_path=root / "state.json",
            codex_home=codex_home,
            group_workdir=root / "group-workspace",
            group_codex_home=root / "group-codex-home",
        )
        self.api = FakeTelegramAPI()
        self.app = AgentApp(config, self.api)
        self.app._bot_username = "codex_codeshark_bot"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def update(
        user_id: int,
        text: str,
        chat_type: str = "private",
        *,
        chat_id: int | None = None,
        title: str | None = None,
    ) -> dict:
        chat = {"id": user_id if chat_id is None else chat_id, "type": chat_type}
        if title is not None:
            chat["title"] = title
        return {
            "update_id": 1,
            "message": {
                "from": {"id": user_id},
                "chat": chat,
                "text": text,
            },
        }

    def test_ignores_unauthorized_user(self) -> None:
        self.app._handle_update(self.update(999, "do work"))
        self.assertEqual(self.app.store.pending_count(), 0)
        self.assertEqual(self.api.messages, [])

    def test_help_and_status_are_english(self) -> None:
        self.assertNotRegex(HELP_TEXT, r"[가-힣]")
        self.assertNotRegex(self.app._status_text(), r"[가-힣]")

    def test_ignores_group_message(self) -> None:
        self.app._handle_update(self.update(123, "do work", chat_type="group"))
        self.assertEqual(self.app.store.pending_count(), 0)
        self.assertEqual(self.api.messages, [])

    def test_admin_enables_group_and_members_get_restricted_mentions_only(self) -> None:
        group_id = -100123
        self.app._handle_update(
            self.update(
                123,
                "/enable_group@Codex_codeshark_bot",
                "supergroup",
                chat_id=group_id,
                title="Engineering",
            )
        )
        self.assertTrue(self.app.store.is_group_enabled(group_id))
        self.assertIn("Group access enabled", self.api.messages[-1][1])

        self.api.messages.clear()
        self.app._handle_update(
            self.update(456, "/status", "supergroup", chat_id=group_id)
        )
        self.assertEqual(self.api.messages, [])

        self.app._handle_update(
            self.update(
                456,
                "@Codex_codeshark_bot Explain Python",
                "supergroup",
                chat_id=group_id,
            )
        )
        task = self.app.store.claim_next_task()
        self.assertTrue(task.ephemeral)
        self.assertTrue(task.restricted)
        self.assertEqual(task.requester_id, 456)
        self.assertEqual(task.source, "telegram-group")
        self.assertEqual(self.api.messages, [])

    def test_group_context_continues_per_requester_without_cross_user_leakage(self) -> None:
        group_id = -100123
        self.app.store.enable_group(group_id, "Engineering", 123)
        runner = FakeCodexRunner()
        self.app.runner = runner

        def run_group(user_id: int, request: str) -> str:
            self.app._handle_update(
                self.update(
                    user_id,
                    f"@Codex_codeshark_bot {request}",
                    "group",
                    chat_id=group_id,
                )
            )
            task = self.app.store.claim_next_task()
            self.app._execute_task(task)
            self.app.store.finish_task(task.id, "completed")
            return runner.prompts[-1][0]

        run_group(456, "My topic is Python")
        other_prompt = run_group(789, "What topic did I choose?")
        same_prompt = run_group(456, "What topic did I choose?")

        self.assertNotIn("My topic is Python", other_prompt)
        self.assertIn("My topic is Python", same_prompt)
        self.assertIn("Recent conversation with this requester", same_prompt)

    def test_group_task_has_no_admin_context_session_learning_or_write_access(self) -> None:
        group_id = -100123
        self.app.store.enable_group(group_id, "Engineering", 123)
        self.app.memory.add("Private administrator memory")
        result = RunResult(
            exit_code=0,
            message=(
                "public answer\n<learning_candidate>"
                '{"kind":"memory","title":"Guest","content":"Do not store"}'
                "</learning_candidate>"
            ),
            thread_id="must-not-persist",
            stderr="",
        )
        runner = FakeCodexRunner(result)
        self.app.runner = runner
        self.app._handle_update(
            self.update(
                456,
                "Explain Python @Codex_codeshark_bot",
                "group",
                chat_id=group_id,
            )
        )
        task = self.app.store.claim_next_task()
        self.app._execute_task(task)

        prompt, thread_id, ephemeral, restricted = runner.prompts[0]
        self.assertNotIn("Private administrator memory", prompt)
        self.assertIn("non-privileged", prompt)
        self.assertIsNone(thread_id)
        self.assertTrue(ephemeral)
        self.assertTrue(restricted)
        self.assertIsNone(self.app.state.snapshot().codex_thread_id)
        self.assertEqual(self.app.learning.list_pending(), [])
        self.assertEqual(self.api.messages[-1], (group_id, "public answer"))

    def test_group_risky_request_is_denied_without_queuing(self) -> None:
        group_id = -100123
        self.app.store.enable_group(group_id, "Engineering", 123)
        self.app._handle_update(
            self.update(
                456,
                "@Codex_codeshark_bot deploy to production",
                "group",
                chat_id=group_id,
            )
        )
        self.assertEqual(self.app.store.pending_count(), 0)
        self.assertIn("administrator privileges", self.api.messages[-1][1])

    def test_only_paired_admin_can_manage_group_access(self) -> None:
        group_id = -100123
        self.app._handle_update(
            self.update(456, "/enable_group", "group", chat_id=group_id)
        )
        self.assertFalse(self.app.store.is_group_enabled(group_id))
        self.assertEqual(self.api.messages, [])

        self.app.store.enable_group(group_id, "Engineering", 123)
        self.app._handle_update(
            self.update(456, "/disable_group", "group", chat_id=group_id)
        )
        self.assertTrue(self.app.store.is_group_enabled(group_id))

        self.app._handle_update(self.update(123, "/groups"))
        self.assertIn("Engineering", self.api.messages[-1][1])
        self.app._handle_update(self.update(123, f"/disable_group {group_id}"))
        self.assertFalse(self.app.store.is_group_enabled(group_id))

    def test_queues_authorized_private_message(self) -> None:
        self.app._handle_update(self.update(123, "do work"))
        self.assertEqual(self.app.store.pending_count(), 1)
        self.assertEqual(self.api.messages, [])

    def test_remember_list_and_forget_commands(self) -> None:
        self.app._handle_update(self.update(123, "/remember Answer in English"))
        self.assertIn("m1", self.api.messages[-1][1])

        self.app._handle_update(self.update(123, "/memories"))
        self.assertIn("Answer in English", self.api.messages[-1][1])

        self.app._handle_update(self.update(123, "/forget m1"))
        self.assertIn("Deleted", self.api.messages[-1][1])
        self.assertEqual(self.app.memory.list(), [])

    def test_new_deletes_current_session_before_clearing_it(self) -> None:
        runner = FakeCodexRunner()
        self.app.runner = runner
        self.app.state.set_codex_thread_id("thread-1")
        self.app._handle_update(self.update(123, "/new"))
        self.assertEqual(runner.deleted_sessions, ["thread-1"])
        self.assertIsNone(self.app.state.snapshot().codex_thread_id)
        self.assertIn("deleted", self.api.messages[-1][1])

    def test_new_keeps_current_session_when_delete_fails(self) -> None:
        runner = FakeCodexRunner()
        runner.delete_error = RuntimeError("delete failed")
        self.app.runner = runner
        self.app.state.set_codex_thread_id("thread-1")
        self.app._handle_update(self.update(123, "/new"))
        self.assertEqual(self.app.state.snapshot().codex_thread_id, "thread-1")
        self.assertIn("could not be deleted", self.api.messages[-1][1])

    def test_new_without_current_session_starts_fresh(self) -> None:
        runner = FakeCodexRunner()
        self.app.runner = runner
        self.app._handle_update(self.update(123, "/new"))
        self.assertEqual(runner.deleted_sessions, [])
        self.assertIsNone(self.app.state.snapshot().codex_thread_id)

    def test_feedback_requires_a_successful_completed_task(self) -> None:
        self.app._handle_update(self.update(123, "/good"))
        self.assertIn("no completed task", self.api.messages[-1][1].lower())

    def test_successful_task_uses_memory_and_accepts_one_feedback(self) -> None:
        self.app.memory.add("Answer in English")
        runner = FakeCodexRunner()
        self.app.runner = runner
        self.app._handle_update(self.update(123, "do work"))
        task = self.app.store.claim_next_task()
        self.app._execute_task(task)

        self.assertIn("Answer in English", runner.prompts[0][0])
        self.assertTrue(runner.prompts[0][0].endswith("do work"))
        self.app._handle_update(self.update(123, "/good accurate"))
        feedback_path = self.app.config.state_path.parent / "feedback.jsonl"
        event = json.loads(feedback_path.read_text(encoding="utf-8"))
        self.assertEqual(event["rating"], "good")
        self.assertEqual(event["note"], "accurate")

        self.app._handle_update(self.update(123, "/good"))
        self.assertIn("no completed task", self.api.messages[-1][1].lower())

    def test_unsuccessful_tasks_are_not_available_for_feedback(self) -> None:
        results = [
            RunResult(exit_code=1, message="", thread_id="failed", stderr="failed"),
            RunResult(exit_code=-15, message="", thread_id="cancelled", stderr="", cancelled=True),
            RunResult(exit_code=-15, message="", thread_id="timed-out", stderr="", timed_out=True),
        ]
        for result in results:
            with self.subTest(thread_id=result.thread_id):
                self.app.runner = FakeCodexRunner(result)
                self.app._handle_update(self.update(123, "do work"))
                task = self.app.store.claim_next_task()
                self.app._execute_task(task)

                self.app._handle_update(self.update(123, "/bad failed"))
                self.assertIn("no completed task", self.api.messages[-1][1].lower())
                self.assertFalse((self.app.config.state_path.parent / "feedback.jsonl").exists())

    def test_risky_task_waits_for_explicit_approval(self) -> None:
        self.app._handle_update(self.update(123, "deploy to production"))
        task = self.app.store.list_tasks()[0]
        self.assertEqual(task.status, "awaiting_approval")
        self.assertIsNone(self.app.store.claim_next_task())

        self.app._handle_update(self.update(123, f"/approve {task.id}"))
        approved = self.app.store.claim_next_task()
        self.assertEqual(approved.id, task.id)
        self.assertTrue(approved.approved)
        runner = FakeCodexRunner()
        self.app.runner = runner
        self.app._execute_task(approved)
        self.assertIn("explicitly approved", runner.prompts[0][0])

    def test_schedule_commands_and_telegram_safe_aliases(self) -> None:
        self.app._handle_update(self.update(123, "/remind 5 check status"))
        self.app._handle_update(self.update(123, "/heartbeat 10 check logs"))
        self.app._handle_update(self.update(123, "/cron */15 * * * * | check metrics"))
        schedules = self.app.store.list_schedules()
        self.assertEqual(len(schedules), 3)

        job_id = schedules[0].id
        self.app._handle_update(self.update(123, f"/pause {job_id}"))
        self.assertEqual(self.app.store.get_schedule(job_id).status, "paused")
        self.app._handle_update(self.update(123, f"/resume_job {job_id}"))
        self.assertEqual(self.app.store.get_schedule(job_id).status, "enabled")
        self.app._handle_update(self.update(123, f"/delete_job {job_id}"))
        self.assertIsNone(self.app.store.get_schedule(job_id))

        self.app.skills.add("Testing", "Test procedure")
        skill_id = self.app.skills.list()[0].id
        self.app._handle_update(self.update(123, f"/forget_skill {skill_id}"))
        self.assertEqual(self.app.skills.list(), [])

    def test_manual_learning_is_applied_immediately(self) -> None:
        self.app._handle_update(self.update(123, "/learn memory The user prefers concise replies"))
        self.assertEqual(self.app.memory.list()[0].text, "The user prefers concise replies")
        self.assertEqual(self.app.learning.list_recent()[0].status, "approved")
        self.assertIn("Learned memory", self.api.messages[-1][1])

    def test_approved_skill_is_loaded_only_for_relevant_task(self) -> None:
        self.app._handle_update(
            self.update(123, "/learn skill Python testing | Run tests with unittest")
        )
        runner = FakeCodexRunner()
        self.app.runner = runner

        self.app._handle_update(self.update(123, "Run the Python unittest tests"))
        task = self.app.store.claim_next_task()
        self.app._execute_task(task)
        self.assertIn("Run tests with unittest", runner.prompts[0][0])

    def test_model_learning_marker_is_hidden_and_applied_automatically(self) -> None:
        result = RunResult(
            exit_code=0,
            message=(
                "done\n<learning_candidate>"
                '{"kind":"memory","title":"Preference","content":"The user prefers English"}'
                "</learning_candidate>"
            ),
            thread_id="thread-new",
            stderr="",
        )
        self.app.runner = FakeCodexRunner(result)
        self.app._handle_update(self.update(123, "do work"))
        task = self.app.store.claim_next_task()
        self.app._execute_task(task)
        event = self.app.learning.list_recent()[0]
        self.assertEqual(event.kind, "memory")
        self.assertEqual(event.status, "approved")
        self.assertEqual(self.app.memory.list()[0].title, "Preference")
        self.assertEqual(self.api.messages, [(123, "done")])
        self.assertFalse(any("<learning_candidate>" in text for _, text in self.api.messages))

    def test_task_sends_only_the_final_result(self) -> None:
        self.app.runner = FakeCodexRunner()
        self.app._handle_update(self.update(123, "do work"))
        self.assertEqual(self.api.messages, [])
        task = self.app.store.claim_next_task()
        self.app._execute_task(task)
        self.assertEqual(self.api.messages, [(123, "done")])

    def test_document_is_saved_inside_workspace_and_queued_without_progress(self) -> None:
        update = self.update(123, "unused")
        update["message"].pop("text")
        update["message"]["caption"] = "Review this file"
        update["message"]["document"] = {
            "file_id": "file-1",
            "file_name": "../../report.txt",
            "file_size": 10,
        }
        self.app._handle_update(update)
        task = self.app.store.claim_next_task()
        self.assertIn("Review this file", task.prompt)
        self.assertRegex(task.prompt, r"inbox/[0-9a-f]{12}-report\.txt")
        attachment = next((self.app.config.workdir / "inbox").iterdir())
        self.assertEqual(attachment.read_bytes(), b"attachment")
        self.assertEqual(self.api.messages, [])

    def test_oversized_attachment_is_rejected_before_download(self) -> None:
        update = self.update(123, "unused")
        update["message"].pop("text")
        update["message"]["document"] = {
            "file_id": "file-1",
            "file_name": "large.bin",
            "file_size": self.app.config.attachment_max_bytes + 1,
        }
        self.app._handle_update(update)
        self.assertEqual(self.app.store.pending_count(), 0)
        self.assertIn("exceeds", self.api.messages[-1][1])

    def test_attachment_is_deleted_when_queue_is_full(self) -> None:
        for number in range(self.app.config.queue_size):
            self.app._handle_update(self.update(123, f"task {number}"))
        update = self.update(123, "unused")
        update["message"].pop("text")
        update["message"]["document"] = {
            "file_id": "file-1",
            "file_name": "report.txt",
            "file_size": 10,
        }
        self.app._handle_update(update)
        self.assertEqual(list((self.app.config.workdir / "inbox").iterdir()), [])
        self.assertIn("queue is full", self.api.messages[-1][1].lower())

    def test_failed_reply_is_persisted_for_explicit_retry(self) -> None:
        class FailingAPI(FakeTelegramAPI):
            def send_message(self, chat_id, text) -> None:
                raise TelegramError("offline", ambiguous_delivery=True)

        self.app.api = FailingAPI()
        self.assertFalse(self.app._send_message(123, "final result"))
        delivery = self.app.store.list_failed_deliveries()[0]
        self.assertEqual(delivery.text, "final result")
        self.assertEqual(delivery.attempts, 1)

    def test_recall_and_feedback_quality_are_visible(self) -> None:
        self.app._handle_update(self.update(123, "/remember Prefer unittest for Python"))
        self.app._handle_update(self.update(123, "/recall unittest"))
        self.assertIn("source=m1", self.api.messages[-1][1])

        self.app.runner = FakeCodexRunner()
        self.app._handle_update(self.update(123, "do work"))
        task = self.app.store.claim_next_task()
        self.app._execute_task(task)
        self.app._handle_update(self.update(123, "/good"))
        stats = self.app.recall.stats("memory", "m1")
        self.assertEqual((stats.use_count, stats.good_count), (1, 1))
        self.app._handle_update(self.update(123, "/memories"))
        self.assertIn("uses=1, good=1, bad=0", self.api.messages[-1][1])

    def test_due_reminder_runs_in_ephemeral_session(self) -> None:
        schedule = self.app.store.create_schedule(
            123,
            kind="once",
            expression="",
            prompt="check server",
            next_run_at=0,
        )
        self.assertIsNotNone(schedule)
        self.app.store.enqueue_due_schedules()
        task = self.app.store.claim_next_task()
        runner = FakeCodexRunner()
        self.app.runner = runner
        self.app._execute_task(task)
        self.assertTrue(runner.prompts[0][2])
        self.assertIsNone(self.app.state.snapshot().codex_thread_id)

    def test_rotates_full_session_after_applying_summary(self) -> None:
        for _ in range(self.app.config.max_session_turns):
            self.app.state.record_codex_turn("thread-old")
        summary = RunResult(
            exit_code=0,
            message=(
                "<learning_candidate>"
                '{"kind":"memory","title":"Summary","content":"Durable fact"}'
                "</learning_candidate>"
            ),
            thread_id="thread-old",
            stderr="",
        )
        runner = FakeCodexRunner(summary)
        runner.results.append(
            RunResult(exit_code=0, message="done", thread_id="thread-new", stderr="")
        )
        self.app.runner = runner
        self.app._handle_update(self.update(123, "do work"))
        task = self.app.store.claim_next_task()
        self.app._execute_task(task)
        self.assertEqual(runner.deleted_sessions, ["thread-old"])
        self.assertEqual(self.app.state.snapshot().codex_thread_id, "thread-new")
        self.assertEqual(self.app.memory.list()[0].title, "Summary")
        self.assertEqual(self.app.learning.list_recent()[0].status, "approved")


if __name__ == "__main__":
    unittest.main()
