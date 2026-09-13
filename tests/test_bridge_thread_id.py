"""Tests for spec-010's bridge.py POST /prompt thread_id/fresh isolation (contracts C3).

Stubs subprocess.run so no real `codex` CLI call happens; drives the real
CodexBridgeServer/CodexBridgeHandler over a loopback socket. See
specs/010-persistent-exec-session/contracts/cli-and-bridge.md C3 and R2.
"""

from __future__ import annotations

import http.client
import http.server
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
import bridge  # noqa: E402


class _FakeCompletedProcess:
    def __init__(self, stdout: str = "", stderr: str = "", returncode: int = 0) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def _fake_subprocess_run(thread_id: str | None, returncode: int, stderr: str = ""):
    """Build a subprocess.run stand-in that writes the -o tmpfile like `codex exec` would."""

    def run(cmd, input=None, capture_output=None, text=None, timeout=None, cwd=None):
        events = []
        if thread_id is not None:
            events.append(json.dumps({"type": "thread.started", "thread_id": thread_id}))
        events.append(json.dumps({"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": 1}}))
        if "-o" in cmd:
            out_path = cmd[cmd.index("-o") + 1]
            with open(out_path, "w") as handle:
                handle.write("stub response" if returncode == 0 else "")
        return _FakeCompletedProcess(stdout="\n".join(events), stderr=stderr, returncode=returncode)

    return run


class BridgeThreadIdTest(unittest.TestCase):
    TOKEN = "test-token"

    def setUp(self) -> None:
        os.environ["CODEX_BRIDGE_TOKEN"] = self.TOKEN
        self.server = bridge.CodexBridgeServer(
            ("127.0.0.1", 0),
            bridge.CodexBridgeHandler,
            timeout=5,
            default_model="gpt-6-astra",
            workdir=str(REPO_ROOT),
            sandbox="workspace-write",
            logger=lambda *_: None,
        )
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def _post(self, body: dict) -> tuple[int, dict]:
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            conn.request(
                "POST", "/prompt", body=json.dumps(body),
                headers={"X-Auth-Token": self.TOKEN, "Content-Type": "application/json"},
            )
            resp = conn.getresponse()
            data = json.loads(resp.read().decode())
            return resp.status, data
        finally:
            conn.close()

    # -- T005 ---------------------------------------------------------------

    def test_thread_id_resume_path(self) -> None:
        with mock.patch.object(bridge.subprocess, "run", _fake_subprocess_run("thread-resumed", 0)):
            status, data = self._post({"prompt": "hi", "thread_id": "thread-existing"})
        self.assertEqual(status, 200)
        self.assertEqual(data["thread_id"], "thread-resumed")
        self.assertFalse(data["session_restarted"])

    def test_thread_id_resume_failure_returns_409(self) -> None:
        with mock.patch.object(bridge.subprocess, "run", _fake_subprocess_run(None, 1, stderr="boom")):
            status, data = self._post({"prompt": "hi", "thread_id": "thread-gone"})
        self.assertEqual(status, 409)
        self.assertEqual(data["error"], "resume failed")
        self.assertEqual(data["thread_id"], "thread-gone")

    def test_global_thread_path_unaffected_when_thread_id_absent(self) -> None:
        with mock.patch.object(bridge.subprocess, "run", _fake_subprocess_run("thread-global-1", 0)):
            status1, data1 = self._post({"prompt": "hi"})
        self.assertEqual(status1, 200)
        self.assertEqual(self.server.thread_id, "thread-global-1")
        with mock.patch.object(bridge.subprocess, "run", side_effect=_fake_subprocess_run("thread-global-2", 0)) as run_mock:
            status2, data2 = self._post({"prompt": "again"})
            called_cmd = run_mock.call_args[0][0]
        self.assertEqual(status2, 200)
        self.assertIn("resume", called_cmd)
        self.assertIn("thread-global-1", called_cmd)
        self.assertEqual(self.server.thread_id, "thread-global-2")

    def test_reset_and_thread_id_mutually_exclusive_400(self) -> None:
        status, data = self._post({"prompt": "hi", "thread_id": "t", "reset": True})
        self.assertEqual(status, 400)

    def test_thread_id_path_returns_request_local_id_and_leaves_global_unchanged(self) -> None:
        with mock.patch.object(bridge.subprocess, "run", _fake_subprocess_run("thread-global-seed", 0)):
            self._post({"prompt": "seed"})
        before = self.server.thread_id
        self.assertEqual(before, "thread-global-seed")

        with mock.patch.object(bridge.subprocess, "run", _fake_subprocess_run("thread-observed", 0)):
            status, data = self._post({"prompt": "isolated", "thread_id": "thread-caller-supplied"})
        self.assertEqual(status, 200)
        self.assertEqual(data["thread_id"], "thread-observed")
        self.assertEqual(self.server.thread_id, before, "global thread must be byte-identical after an isolated request")

        # and again on the 409 path
        with mock.patch.object(bridge.subprocess, "run", _fake_subprocess_run(None, 1, stderr="down")):
            status2, _ = self._post({"prompt": "isolated-fail", "thread_id": "thread-caller-supplied"})
        self.assertEqual(status2, 409)
        self.assertEqual(self.server.thread_id, before, "global thread must be unchanged even on 409")

    def test_fresh_true_builds_command_without_resume_and_leaves_global_unchanged(self) -> None:
        with mock.patch.object(bridge.subprocess, "run", _fake_subprocess_run("thread-global-seed2", 0)):
            self._post({"prompt": "seed"})
        before = self.server.thread_id
        self.assertIsNotNone(before)

        with mock.patch.object(bridge.subprocess, "run", side_effect=_fake_subprocess_run("thread-fresh-observed", 0)) as run_mock:
            status, data = self._post({"prompt": "fresh please", "fresh": True})
            called_cmd = run_mock.call_args[0][0]
        self.assertEqual(status, 200)
        self.assertNotIn("resume", called_cmd)
        self.assertEqual(data["thread_id"], "thread-fresh-observed")
        self.assertEqual(self.server.thread_id, before)

    def test_fresh_and_thread_id_together_400(self) -> None:
        status, _ = self._post({"prompt": "hi", "thread_id": "t", "fresh": True})
        self.assertEqual(status, 400)
        status2, _ = self._post({"prompt": "hi", "fresh": True, "reset": True})
        self.assertEqual(status2, 400)

    # -- T041: a mandate dispatch must never disturb a pending follow-up's thread --

    def test_mandate_dispatch_does_not_disturb_pending_followup_thread(self) -> None:
        with mock.patch.object(bridge.subprocess, "run", _fake_subprocess_run("global-followup-thread", 0)):
            self._post({"prompt": "parent turn"})
        global_before = self.server.thread_id
        self.assertEqual(global_before, "global-followup-thread")

        # An isolated mandate dispatch happens in between (caller-supplied thread_id).
        with mock.patch.object(bridge.subprocess, "run", _fake_subprocess_run("mandate-role-thread", 0)):
            self._post({"prompt": "mandate role ping", "thread_id": "mandate-role-thread"})
        self.assertEqual(self.server.thread_id, global_before)

        # The pending follow-up (global path, no thread_id) still resumes the ORIGINAL thread.
        with mock.patch.object(bridge.subprocess, "run", side_effect=_fake_subprocess_run("global-followup-thread-2", 0)) as run_mock:
            status, _ = self._post({"prompt": "follow-up turn"})
            called_cmd = run_mock.call_args[0][0]
        self.assertEqual(status, 200)
        self.assertIn("resume", called_cmd)
        self.assertIn(global_before, called_cmd)


class AskShBodyShapeTest(unittest.TestCase):
    """T046: ask.sh's POST body omits thread_id entirely when --thread is absent."""

    class _RecordingHandler(http.server.BaseHTTPRequestHandler):
        captured_body: dict | None = None

        def do_POST(self) -> None:  # noqa: N802 (stdlib override name)
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            type(self).captured_body = json.loads(body.decode())
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"response": "ok", "thread_id": "t", "usage": {}}).encode())

        def log_message(self, format, *args):  # noqa: A002 (stdlib signature)
            pass

    def setUp(self) -> None:
        self.__class__._RecordingHandler.captured_body = None
        self.recording_server = http.server.HTTPServer(("127.0.0.1", 0), self._RecordingHandler)
        self.port = self.recording_server.server_address[1]
        self.thread = threading.Thread(target=self.recording_server.serve_forever, daemon=True)
        self.thread.start()

        self._tmp = tempfile.TemporaryDirectory()
        fake_home = Path(self._tmp.name)
        bridge_dir = fake_home / ".codex-bridge"
        bridge_dir.mkdir(parents=True)
        (bridge_dir / "token").write_text("fake-token")
        (bridge_dir / "state.json").write_text(json.dumps({"port": self.port, "timeout": 30}))
        self.fake_home = fake_home
        self.ask_sh = REPO_ROOT / "skills" / "codex-bridge" / "scripts" / "ask.sh"

    def tearDown(self) -> None:
        self.recording_server.shutdown()
        self.recording_server.server_close()
        self.thread.join(timeout=5)
        self._tmp.cleanup()

    def _run_ask(self, *extra_args: str) -> subprocess.CompletedProcess:
        env = os.environ.copy()
        env["HOME"] = str(self.fake_home)
        return subprocess.run(
            [str(self.ask_sh), *extra_args, "hello"],
            env=env, capture_output=True, text=True, timeout=15,
        )

    def test_ask_sh_body_omits_thread_id_when_flag_absent(self) -> None:
        result = self._run_ask("--raw")
        self.assertEqual(result.returncode, 0, result.stderr)
        body = self._RecordingHandler.captured_body
        self.assertIsNotNone(body)
        self.assertNotIn("thread_id", body)
        self.assertNotIn("fresh", body)

    def test_ask_sh_body_includes_thread_id_when_flag_present(self) -> None:
        result = self._run_ask("--raw", "--thread", "T-123")
        self.assertEqual(result.returncode, 0, result.stderr)
        body = self._RecordingHandler.captured_body
        self.assertEqual(body.get("thread_id"), "T-123")
        self.assertNotIn("fresh", body)

    def test_ask_sh_thread_and_fresh_together_refused(self) -> None:
        result = self._run_ask("--thread", "T-1", "--fresh")
        self.assertEqual(result.returncode, 2)


if __name__ == "__main__":
    unittest.main()
