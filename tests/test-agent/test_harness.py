import io
import json
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import agent
import lib_test
import run


class HarnessTests(unittest.TestCase):
    def test_prompt_examples_survive_formatting(self):
        prompt = agent.SYSTEM.format(workspace="/tmp/workspace", state="/tmp/workspace/state",
                                     repo="/tmp/repo with spaces", index="file-read",
                                     todo_example=agent.TODO_EXAMPLE)
        self.assertIn('{"name":"file-read","argv":["note.txt"]}', prompt)
        self.assertIn(agent.TODO_EXAMPLE, prompt)
        self.assertEqual(json.loads(agent.TODO_EXAMPLE)["argv"][0], "set")

    def test_plain_final_answer_is_accepted(self):
        self.assertEqual(
            lib_test.parse_reply({"role": "assistant", "content": "The first step is in_progress."}),
            {"kind": "finish", "answer": "The first step is in_progress."},
        )

    def test_plain_final_answer_can_contain_json_example(self):
        text = 'Valid manifests:\n```json\n{"ok": true}\n```'
        self.assertEqual(lib_test.parse_reply({"role": "assistant", "content": text})["kind"],
                         "finish")

    def test_structured_argv_preserves_argument_boundaries(self):
        reply = {"tool_calls": [{"function": {"name": "tool_call", "arguments":
                 json.dumps({"name": "plan-todo", "argv": ["set", "--todos",
                 '[{"content":"write tests","status":"in_progress"}]']})}}]}
        parsed = lib_test.parse_reply(reply)
        self.assertEqual(parsed["argv"], ["set", "--todos",
                         '[{"content":"write tests","status":"in_progress"}]'])
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(agent.subprocess, "run") as execute:
                execute.return_value.returncode = 0
                execute.return_value.stdout = "[]"
                execute.return_value.stderr = ""
                result = agent.run_tool(lib_test.load_tool_manifests(), "plan-todo",
                                        parsed["argv"], Path(directory))
            self.assertEqual(execute.call_args.args[0][-3:], parsed["argv"])
            self.assertEqual(result["exit"], 0)

    def test_run_shell_propagates_nested_command_failure(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(agent.subprocess, "run") as execute:
            execute.return_value.returncode = 0
            execute.return_value.stdout = json.dumps({
                "exit": 7, "stdout": "", "stderr": "command failed"})
            execute.return_value.stderr = ""
            result = agent.run_tool(lib_test.load_tool_manifests(), "run-shell",
                                    ["false"], Path(directory))
        self.assertEqual(result["exit"], 7)
        self.assertEqual(result["stderr"], "command failed")

    def test_dependency_tool_uses_isolated_python(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(agent.subprocess, "run") as execute:
            execute.return_value.returncode = 0
            execute.return_value.stdout = "{}"
            execute.return_value.stderr = ""
            agent.run_tool(lib_test.load_tool_manifests(), "web-fetch",
                           ["https://example.com"], Path(directory))
        self.assertEqual(execute.call_args.args[0][0],
                         str(agent.REPO_ROOT / ".venv/bin/python"))

    def test_run_shell_combines_command_tokens_before_flags(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(agent.subprocess, "run") as execute:
            execute.return_value.returncode = 0
            execute.return_value.stdout = '{"exit":0,"stdout":"ok","stderr":""}'
            execute.return_value.stderr = ""
            result = agent.run_tool(lib_test.load_tool_manifests(), "run-shell",
                                    ["bash", "tests/mcp-serve/smoke.sh", "--cwd", directory],
                                    Path(directory))
        self.assertEqual(result["exit"], 0)
        self.assertEqual(execute.call_args.args[0][-3:],
                         ["bash tests/mcp-serve/smoke.sh", "--cwd", directory])

    def test_run_shell_accepts_cwd_flag_after_command(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(agent.subprocess, "run") as execute:
            execute.return_value.returncode = 0
            execute.return_value.stdout = '{"exit":0,"stdout":"ok","stderr":""}'
            execute.return_value.stderr = ""
            result = agent.run_tool(lib_test.load_tool_manifests(), "run-shell",
                                    ["echo ok", "--cwd", directory], Path(directory))
        self.assertEqual(result["exit"], 0)
        self.assertEqual(execute.call_args.args[0][-3:],
                         ["echo ok", "--cwd", directory])

    def test_run_shell_redirects_indirect_tool_calls(self):
        with tempfile.TemporaryDirectory() as directory:
            result = agent.run_tool(lib_test.load_tool_manifests(), "run-shell",
                                    ["python3 tools/selftest/selftest.py --manifests-only"],
                                    Path(directory))
        self.assertEqual(result["exit"], 2)
        self.assertIn("name='selftest'", result["stderr"])

    def test_native_tool_turn_is_replayed_with_matching_id(self):
        call = {"id": "call-1", "type": "function", "function": {
            "name": "tool_call", "arguments": '{"name":"file-read","args":"note.txt"}'}}
        response = {"role": "assistant", "content": "", "reasoning": "Private reasoning",
                    "tool_calls": [call]}
        messages = []
        agent.record_tool_turn(messages, response, "file-read", "note.txt", "second line")
        self.assertEqual(messages, [
            {"role": "assistant", "content": "", "reasoning": "Private reasoning",
             "tool_calls": [call]},
            {"role": "tool", "tool_call_id": "call-1", "content": "second line"},
        ])

    def test_http_failure_includes_server_diagnostics(self):
        error = urllib.error.HTTPError("http://localhost/v1/chat/completions", 400,
                                       "Bad Request", {}, io.BytesIO(b'{"error":"context too long"}'))
        with patch.object(lib_test.urllib.request, "urlopen", side_effect=error), \
                self.assertRaisesRegex(lib_test.LLMHTTPError, "context too long") as raised:
            lib_test.chat([{"role": "user", "content": "hi"}])
        self.assertEqual(raised.exception.status, 400)

    def test_streaming_response_reassembles_reasoning_and_tool_arguments(self):
        chunks = [
            {"choices": [{"delta": {"role": "assistant", "reasoning": "Need tool."}}]},
            {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "c1",
                "type": "function", "function": {"name": "tool_call", "arguments": '{"name":'}}]}}]},
            {"choices": [{"delta": {"tool_calls": [{"index": 0,
                "function": {"arguments": '"file-read","args":"note.txt"}'}}]}}]},
        ]
        response = io.BytesIO(b"".join(b"data: " + json.dumps(c).encode() + b"\n\n"
                                        for c in chunks) + b"data: [DONE]\n\n")
        with patch.object(lib_test.urllib.request, "urlopen", return_value=response):
            msg = lib_test.chat([{"role": "user", "content": "hi"}], stream=True)
        self.assertEqual(msg["reasoning"], "Need tool.")
        self.assertEqual(json.loads(msg["tool_calls"][0]["function"]["arguments"]),
                         {"name": "file-read", "args": "note.txt"})

    def test_streaming_response_missing_done_does_not_complete(self):
        response = io.BytesIO(b'data: {"choices":[{"delta":{"content":"partial"}}]}\n\n')
        with patch.object(lib_test.urllib.request, "urlopen", return_value=response), \
                self.assertRaisesRegex(ValueError, "ended before completion"):
            lib_test.chat([{"role": "user", "content": "hi"}], stream=True)

    def test_numeric_answers_accept_grouping_but_not_wrong_values(self):
        expected = {"answer_contains": ["18446744073709551616"]}
        self.assertEqual(lib_test.validate({"answer": "18,446,744,073,709,551,616"},
                                           expected, Path("/tmp")), [])
        self.assertTrue(lib_test.validate({"answer": "18,446,744,073,709,551,617"},
                                          expected, Path("/tmp")))

    def test_file_contains_matches_case_insensitively(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            (workspace / "health.md").write_text("**Current Branch:** main\n")
            expected = {"files": [{"path": "health.md", "contains": "branch"}]}
            self.assertEqual(lib_test.validate({}, expected, workspace), [])

    def test_absent_artifact_check_rejects_leftover_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            (workspace / "scratch").mkdir()
            expected = {"absent": ["scratch"]}
            self.assertEqual(lib_test.validate({}, expected, workspace),
                             ["expected 'scratch' to be absent"])
            (workspace / "scratch").rmdir()
            self.assertEqual(lib_test.validate({}, expected, workspace), [])

    def test_suite_reports_unknown_as_failure(self):
        self.assertTrue(run.suite_failed({"FAILED": 0, "STUCK": 0, "UNKNOWN": 1}))
        self.assertFalse(run.suite_failed({"FAILED": 0, "STUCK": 0, "UNKNOWN": 0}))

    def test_json_fallback_only_on_protocol_error(self):
        self.assertTrue(agent.can_fallback_to_json(lib_test.LLMHTTPError(400, "bad request")))
        self.assertFalse(agent.can_fallback_to_json(lib_test.LLMHTTPError(503, "unavailable")))
        self.assertFalse(agent.can_fallback_to_json(TimeoutError("timeout")))

    def test_qwen35_uses_non_greedy_model_card_sampling(self):
        # Greedy decoding makes Qwen3.5 thinking mode loop on identical calls.
        qwen = lib_test.sampling_for("qwen/qwen3.5-9b")
        self.assertGreater(qwen["temperature"], 0)
        self.assertEqual(lib_test.sampling_for("other/model")["temperature"], 0)

    def test_judge_falls_back_to_reasoning_verdict(self):
        # Thinking models can exhaust max_tokens on reasoning and leave
        # content empty; the verdict may still appear in reasoning.
        msg = {"role": "assistant", "content": "",
               "reasoning_content": '{"pass": true, "reason": "rubric met"}'}
        with patch.object(lib_test, "chat", return_value=msg):
            verdict = lib_test.judge("task", "rubric", "answer", [], [])
        self.assertTrue(verdict["pass"])
        self.assertEqual(verdict["reason"], "rubric met")

    def test_chat_body_uses_model_sampling_profile(self):
        captured = {}

        def fake_urlopen(req, timeout=None):
            captured.update(json.loads(req.data))
            payload = {"choices": [{"message": {"role": "assistant",
                                                "content": "ok"}}]}
            return io.BytesIO(json.dumps(payload).encode())

        with patch.object(lib_test.urllib.request, "urlopen", fake_urlopen):
            lib_test.chat([{"role": "user", "content": "hi"}],
                          model="qwen/qwen3.5-9b", stream=False)
        self.assertEqual(captured["temperature"], 0.6)
        self.assertEqual(captured["top_p"], 0.95)


if __name__ == "__main__":
    unittest.main()
