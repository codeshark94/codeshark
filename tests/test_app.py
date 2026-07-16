import json
import tempfile
import unittest
from pathlib import Path

from codex_codeshark.app import AgentApp
from codex_codeshark.codex_runner import RunResult
from codex_codeshark.config import Config


class FakeTelegramAPI:
    def __init__(self) -> None:
        self.messages = []

    def send_message(self, chat_id, text) -> None:
        self.messages.append((chat_id, text))

    def send_typing(self, chat_id) -> None:
        pass


class FakeCodexRunner:
    def __init__(self, result: RunResult | None = None) -> None:
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

    def run(self, prompt, thread_id, *, ephemeral=False) -> RunResult:
        self.prompts.append((prompt, thread_id, ephemeral))
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
        config = Config(
            allowed_user_ids=frozenset({123}),
            workdir=workspace,
            codex_binary=binary,
            state_path=root / "state.json",
        )
        self.api = FakeTelegramAPI()
        self.app = AgentApp(config, self.api)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def update(user_id: int, text: str, chat_type: str = "private") -> dict:
        return {
            "update_id": 1,
            "message": {
                "from": {"id": user_id},
                "chat": {"id": user_id, "type": chat_type},
                "text": text,
            },
        }

    def test_ignores_unauthorized_user(self) -> None:
        self.app._handle_update(self.update(999, "do work"))
        self.assertEqual(self.app.store.pending_count(), 0)
        self.assertEqual(self.api.messages, [])

    def test_ignores_group_message(self) -> None:
        self.app._handle_update(self.update(123, "do work", chat_type="group"))
        self.assertEqual(self.app.store.pending_count(), 0)
        self.assertEqual(self.api.messages, [])

    def test_queues_authorized_private_message(self) -> None:
        self.app._handle_update(self.update(123, "do work"))
        self.assertEqual(self.app.store.pending_count(), 1)
        self.assertIn("접수", self.api.messages[0][1])

    def test_remember_list_and_forget_commands(self) -> None:
        self.app._handle_update(self.update(123, "/remember 답변은 한국어로 한다"))
        self.assertIn("m1", self.api.messages[-1][1])

        self.app._handle_update(self.update(123, "/memories"))
        self.assertIn("답변은 한국어로 한다", self.api.messages[-1][1])

        self.app._handle_update(self.update(123, "/forget m1"))
        self.assertIn("삭제", self.api.messages[-1][1])
        self.assertEqual(self.app.memory.list(), [])

    def test_new_deletes_current_session_before_clearing_it(self) -> None:
        runner = FakeCodexRunner()
        self.app.runner = runner
        self.app.state.set_codex_thread_id("thread-1")
        self.app._handle_update(self.update(123, "/new"))
        self.assertEqual(runner.deleted_sessions, ["thread-1"])
        self.assertIsNone(self.app.state.snapshot().codex_thread_id)
        self.assertIn("삭제", self.api.messages[-1][1])

    def test_new_keeps_current_session_when_delete_fails(self) -> None:
        runner = FakeCodexRunner()
        runner.delete_error = RuntimeError("delete failed")
        self.app.runner = runner
        self.app.state.set_codex_thread_id("thread-1")
        self.app._handle_update(self.update(123, "/new"))
        self.assertEqual(self.app.state.snapshot().codex_thread_id, "thread-1")
        self.assertIn("삭제하지 못했습니다", self.api.messages[-1][1])

    def test_new_without_current_session_starts_fresh(self) -> None:
        runner = FakeCodexRunner()
        self.app.runner = runner
        self.app._handle_update(self.update(123, "/new"))
        self.assertEqual(runner.deleted_sessions, [])
        self.assertIsNone(self.app.state.snapshot().codex_thread_id)

    def test_feedback_requires_a_successful_completed_task(self) -> None:
        self.app._handle_update(self.update(123, "/good"))
        self.assertIn("평가할 완료 작업", self.api.messages[-1][1])

    def test_successful_task_uses_memory_and_accepts_one_feedback(self) -> None:
        self.app.memory.add("답변은 한국어로 한다")
        runner = FakeCodexRunner()
        self.app.runner = runner
        self.app._handle_update(self.update(123, "do work"))
        task = self.app.store.claim_next_task()
        self.app._execute_task(task)

        self.assertIn("답변은 한국어로 한다", runner.prompts[0][0])
        self.assertTrue(runner.prompts[0][0].endswith("do work"))
        self.app._handle_update(self.update(123, "/good 정확함"))
        feedback_path = self.app.config.state_path.parent / "feedback.jsonl"
        event = json.loads(feedback_path.read_text(encoding="utf-8"))
        self.assertEqual(event["rating"], "good")
        self.assertEqual(event["note"], "정확함")

        self.app._handle_update(self.update(123, "/good"))
        self.assertIn("평가할 완료 작업", self.api.messages[-1][1])

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

                self.app._handle_update(self.update(123, "/bad 실패함"))
                self.assertIn("평가할 완료 작업", self.api.messages[-1][1])
                self.assertFalse((self.app.config.state_path.parent / "feedback.jsonl").exists())

    def test_risky_task_waits_for_explicit_approval(self) -> None:
        self.app._handle_update(self.update(123, "운영 서버에 배포해줘"))
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
        self.assertIn("명시적으로 승인", runner.prompts[0][0])

    def test_schedule_commands_and_telegram_safe_aliases(self) -> None:
        self.app._handle_update(self.update(123, "/remind 5 상태 확인"))
        self.app._handle_update(self.update(123, "/heartbeat 10 로그 확인"))
        self.app._handle_update(self.update(123, "/cron */15 * * * * | 지표 확인"))
        schedules = self.app.store.list_schedules()
        self.assertEqual(len(schedules), 3)

        job_id = schedules[0].id
        self.app._handle_update(self.update(123, f"/pause {job_id}"))
        self.assertEqual(self.app.store.get_schedule(job_id).status, "paused")
        self.app._handle_update(self.update(123, f"/resume_job {job_id}"))
        self.assertEqual(self.app.store.get_schedule(job_id).status, "enabled")
        self.app._handle_update(self.update(123, f"/delete_job {job_id}"))
        self.assertIsNone(self.app.store.get_schedule(job_id))

        self.app.skills.add("테스트", "테스트 절차")
        skill_id = self.app.skills.list()[0].id
        self.app._handle_update(self.update(123, f"/forget_skill {skill_id}"))
        self.assertEqual(self.app.skills.list(), [])

    def test_learning_candidate_requires_approval_before_memory_write(self) -> None:
        self.app._handle_update(self.update(123, "/learn memory 사용자는 짧은 답변을 선호한다"))
        candidate = self.app.learning.list_pending()[0]
        self.assertEqual(self.app.memory.list(), [])

        self.app._handle_update(self.update(123, f"/approve {candidate.id}"))
        self.assertEqual(self.app.memory.list()[0].text, "사용자는 짧은 답변을 선호한다")

    def test_approved_skill_is_loaded_only_for_relevant_task(self) -> None:
        self.app._handle_update(
            self.update(123, "/learn skill Python 테스트 | unittest로 테스트를 실행한다")
        )
        candidate = self.app.learning.list_pending()[0]
        self.app._handle_update(self.update(123, f"/approve {candidate.id}"))
        runner = FakeCodexRunner()
        self.app.runner = runner

        self.app._handle_update(self.update(123, "Python unittest 테스트를 실행해줘"))
        task = self.app.store.claim_next_task()
        self.app._execute_task(task)
        self.assertIn("unittest로 테스트를 실행한다", runner.prompts[0][0])

    def test_model_learning_marker_is_hidden_and_staged(self) -> None:
        result = RunResult(
            exit_code=0,
            message=(
                "done\n<learning_candidate>"
                '{"kind":"memory","title":"선호","content":"사용자는 한국어를 선호한다"}'
                "</learning_candidate>"
            ),
            thread_id="thread-new",
            stderr="",
        )
        self.app.runner = FakeCodexRunner(result)
        self.app._handle_update(self.update(123, "do work"))
        task = self.app.store.claim_next_task()
        self.app._execute_task(task)
        self.assertEqual(self.app.learning.list_pending()[0].kind, "memory")
        self.assertTrue(any(text == "done" for _, text in self.api.messages))
        self.assertFalse(any("<learning_candidate>" in text for _, text in self.api.messages))

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

    def test_rotates_full_session_after_staging_summary(self) -> None:
        for _ in range(self.app.config.max_session_turns):
            self.app.state.record_codex_turn("thread-old")
        summary = RunResult(
            exit_code=0,
            message=(
                "<learning_candidate>"
                '{"kind":"memory","title":"요약","content":"지속할 사실"}'
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
        self.assertEqual(self.app.learning.list_pending()[0].title, "요약")


if __name__ == "__main__":
    unittest.main()
