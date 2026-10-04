"""D51 dispatch broker: request validation, fan-out total, atomic outputs, exit codes."""
from __future__ import annotations
import contextlib
import io
import json
import os
import subprocess
import tempfile
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from agents_inc.install import cli, dispatch

REPO = Path(__file__).resolve().parents[1]
EXAMPLE = REPO / "skills/workerbee/tests/fixtures/example_slots.json"
GOOD_REPORT = ("caveman ultra confirmed. GRILL: none. [verified] gate rc=0 exit code 0.\n"
               "OUT OF SCOPE / INCOMPLETE: none\nWORKERS SPAWNED: 0\n")


def _git_repo(root: Path) -> Path:
    repo = root / "repo"
    repo.mkdir()
    for cmd in (["git", "init", "-q"], ["git", "-c", "user.email=t@t", "-c", "user.name=t",
                                        "commit", "-q", "--allow-empty", "-m", "init"]):
        subprocess.run(cmd, cwd=repo, check=True, capture_output=True)
    return repo


class BrokerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.repo = _git_repo(self.root)
        self.run_dir = self.root / "lead-run"
        self.run_dir.mkdir()
        self.inbox = self.run_dir / "inbox"
        self.inbox.mkdir()
        self.env = mock.patch.dict("os.environ", {"HOME": str(self.root)})
        self.env.start()
        os.environ.pop("AGENTS_INC_HOME_REPO", None)
        self.launches = []
        # Request validation needs a sandbox backend for Claude models; tests that check refusal re-patch it.
        self.sb = mock.patch.object(dispatch, "sandbox_available", return_value=True)
        self.sb.start()
        self.addCleanup(self.sb.stop)

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def _manifest(self, total=2, width=1, models=("haiku",), **extra):
        spec = {"schema_version": 1, "run_id": "lead-1", "model": "sol", "effort": "high",
                "cwd": str(self.repo), "chain": ["CoS", "sol"], "worker_models": list(models),
                "fan_out": {"width": width, "total": total, "depth": 1}, "permission_mode": "default"}
        spec.update(extra)
        (self.run_dir / "run.json").write_text(json.dumps(spec))

    def _slots(self):
        return json.loads(EXAMPLE.read_text())

    def _request(self, rid, model="haiku", tier="grunt", via_tmp=True, **over):
        req = {"schema_version": 1, "request_id": rid, "model": model, "effort": "low", "tier": tier,
               "slots": self._slots()}
        req.update(over)
        final = self.inbox / f"{rid}.request.json"
        tmp = final.with_name(final.name + ".tmp")
        tmp.write_text(json.dumps(req) if not isinstance(req, str) else req)
        if via_tmp:
            os.rename(tmp, final)
        return final

    def _fake_launch(self, rc=0, report=GOOD_REPORT):
        def fake(kind, model, effort, cwd, prompt, run_dir, permission_mode="acceptEdits", resume=None):
            self.launches.append({"model": model, "cwd": str(cwd), "permission_mode": permission_mode})
            return {"rc": rc, "stdout": report, "stderr": "", "argv": ["claude"], "session_id": "s"}
        return fake

    def _serve(self, done=True, launch=None, **kw):
        if done:
            (self.inbox / "lead.done").write_text("")
        err = io.StringIO()
        with mock.patch.object(dispatch, "launch", side_effect=launch or self._fake_launch()), \
                contextlib.redirect_stderr(err):
            rc = dispatch.serve(self.run_dir, poll_interval=0.01, idle_timeout=kw.pop("idle", 5), **kw)
        return rc, err.getvalue()

    def _result(self, rid):
        return json.loads((self.run_dir / f"{rid}.result.json").read_text())

    def _spec(self):
        return json.loads((self.run_dir / "run.json").read_text())

    # --- schema ---------------------------------------------------------------
    def test_valid_request_green_and_outputs(self):
        self._manifest()
        self._request("r1")
        rc, err = self._serve()
        self.assertEqual(rc, 0, err)
        res = self._result("r1")
        self.assertEqual((res["status"], res["dispatch_exit_code"], res["outcome"]), ("green", 0, "green"), res)
        for key in ("schema_version", "request_id", "status", "dispatch_exit_code", "child_run_id", "outcome",
                    "reason", "report_path", "started_at", "finished_at"):
            self.assertIn(key, res)
        self.assertEqual(Path(res["report_path"]).read_text(), GOOD_REPORT)
        self.assertEqual(self.launches[0]["cwd"], str(self.repo))
        self.assertEqual(self.launches[0]["permission_mode"], "default")  # from run.json, not the request
        spec = self._spec()
        self.assertEqual(spec["workers_spawned"], 1)
        self.assertEqual(spec["request_counts"]["green"], 1)
        self.assertEqual(spec["broker"]["stop"], "lead-done")
        self.assertFalse((self.inbox / "r1.request.json").exists())
        # child run lives under the broker-owned workers directory
        self.assertTrue((self.run_dir / "workers" / "r1" / "runs" / res["child_run_id"] / "run.json").is_file())

    def test_schema_rejections(self):
        self._manifest(total=9)
        cases = {
            "k1": {"cwd": "/etc"},                       # extra key
            "k2": {"schema_version": 2},
            "k3": {"effort": "turbo"},
            "k4": {"tier": "workhorse"},                 # tier/model mismatch
            "k5": {"slots": {"PERMISSION_MODE": "bypassPermissions"}},
            "k6": {"slots": {"ROLE": 3}},
            "k7": {"request_id": "other"},               # id/filename mismatch
            "k8": {"env": {"X": "1"}},
        }
        for rid, over in cases.items():
            self._request(rid, **over)
        (self.inbox / "k9.request.json").write_text("{not json")
        rc, _ = self._serve()
        self.assertEqual(rc, 0)
        for rid in list(cases) + ["k9"]:
            res = self._result(rid)
            self.assertEqual((res["status"], res["dispatch_exit_code"]), ("refused", 3), rid)
        self.assertEqual(self.launches, [])
        self.assertEqual(self._spec()["workers_spawned"], 0)

    def test_oversize_refused(self):
        self._manifest()
        self._request("big", slots=dict(self._slots(), NOTES="x" * (dispatch.REQUEST_MAX_BYTES + 1)))
        self._serve()
        self.assertEqual(self._result("big")["reason"], "too-large")

    def test_model_allowlist_refusal(self):
        self._manifest(models=("haiku",))
        self._request("s1", model="sonnet", tier="workhorse")
        self._serve()
        self.assertEqual(self._result("s1")["reason"], "model-not-allowed")
        self.assertEqual(self.launches, [])

    # --- path safety ------------------------------------------------------------
    def test_symlink_request_refused(self):
        self._manifest()
        target = self.root / "outside.json"
        target.write_text(json.dumps({"schema_version": 1, "request_id": "ln", "model": "haiku", "effort": "low",
                                      "tier": "grunt", "slots": self._slots()}))
        (self.inbox / "ln.request.json").symlink_to(target)
        self._serve()
        self.assertEqual(self._result("ln")["reason"], "not-regular-file")
        self.assertEqual(self.launches, [])

    def test_traversal_names_ignored(self):
        self._manifest()
        sub = self.inbox / "sub"
        sub.mkdir()
        (self.inbox / "..%2Fx.request.json").write_text("{}")
        (sub / "nested.request.json").write_text("{}")
        rc, _ = self._serve()
        self.assertEqual(rc, 0)
        self.assertEqual(list(self.root.glob("*.result.json")), [])
        self.assertEqual(sorted(p.name for p in self.run_dir.glob("*.result.json")), [])
        self.assertEqual(self.launches, [])

    def test_planted_worker_dir_symlink_fatal_not_followed(self):
        self._manifest()
        outside = self.root / "outside"
        outside.mkdir()
        (self.run_dir / "workers").symlink_to(outside)
        self._request("r1")
        rc, err = self._serve()
        self.assertEqual(rc, 1, err)
        self.assertEqual(list(outside.iterdir()), [])

    # --- duplicates and fan-out -------------------------------------------------
    def test_duplicate_refused_no_second_slot(self):
        self._manifest(total=5)
        self._request("r1")
        self._serve(done=False, idle=0.05)
        first = (self.run_dir / "r1.result.json").read_bytes()
        self._request("r1")
        self._serve()
        self.assertEqual((self.run_dir / "r1.result.json").read_bytes(), first)  # never overwritten
        spec = self._spec()
        self.assertEqual(spec["workers_spawned"], 1)
        self.assertEqual(spec["request_counts"]["duplicate"], 1)
        self.assertEqual(len(self.launches), 1)

    def test_total_cap_refusal(self):
        self._manifest(total=1)
        self._request("a1")
        self._request("a2")
        self._serve()
        self.assertEqual(self._result("a1")["status"], "green")
        self.assertEqual(self._result("a2")["reason"], "fan-out-total-exhausted")
        self.assertEqual(len(self.launches), 1)
        self.assertEqual(self._spec()["workers_spawned"], 1)

    def test_zero_total_refused(self):
        self._manifest(total=0)
        self._request("z1")
        self._serve()
        self.assertEqual(self._result("z1")["reason"], "fan-out-zero")
        self.assertEqual(self.launches, [])

    def test_failed_worker_consumes_total(self):
        self._manifest(total=1)
        self._request("f1")
        self._request("f2")
        self._serve(launch=self._fake_launch(rc=1))
        res = self._result("f1")
        self.assertEqual((res["status"], res["dispatch_exit_code"]), ("red", 1))
        self.assertEqual(self._result("f2")["reason"], "fan-out-total-exhausted")
        self.assertEqual(self._spec()["workers_spawned"], 1)
        self.assertEqual(self._spec()["request_counts"]["red"], 1)

    def test_lint_refusal_releases_slot(self):
        self._manifest(total=1)
        self._request("l1", slots={k: v for k, v in self._slots().items() if k != "OUT_OF_SCOPE"})
        self._request("l2")
        self._serve()
        self.assertEqual(self._result("l1")["dispatch_exit_code"], 3)
        self.assertEqual(self._result("l2")["status"], "green")
        self.assertEqual(self._spec()["workers_spawned"], 1)

    def test_lead_edit_to_run_json_ignored(self):
        self._manifest(total=1)
        for rid in ("a1", "a2", "a3"):
            self._request(rid)
        inner = self._fake_launch()

        def tamper(*a, **k):
            # the Lead (write access to its run dir) tries to widen its budget mid-run
            spec = self._spec()
            spec["workers_spawned"] = 0
            spec["fan_out"]["total"] = 99
            (self.run_dir / "run.json").write_text(json.dumps(spec))
            return inner(*a, **k)
        self._serve(launch=tamper)
        self.assertEqual(len(self.launches), 1)
        self.assertEqual(self._spec()["fan_out"]["total"], 1)
        self.assertEqual(self._spec()["workers_spawned"], 1)

    # --- atomic outputs and recovery --------------------------------------------
    def test_partial_tmp_ignored_then_processed(self):
        self._manifest()
        self._request("p1", via_tmp=False)
        rc, _ = self._serve(done=False, idle=0.05)
        self.assertEqual(rc, 0)
        self.assertFalse((self.run_dir / "p1.result.json").exists())
        os.rename(self.inbox / "p1.request.json.tmp", self.inbox / "p1.request.json")
        self._serve()
        self.assertEqual(self._result("p1")["status"], "green")

    def test_result_never_overwritten(self):
        self._manifest()
        dispatch._write_request_result(self.run_dir, "x1", {"status": "green"}, "r\n")
        with self.assertRaises(FileExistsError):
            dispatch._write_request_result(self.run_dir, "x1", {"status": "red"}, "r\n")
        self.assertEqual(self._result("x1")["status"], "green")
        self.assertEqual([p.name for p in self.run_dir.iterdir() if "broker-tmp" in p.name], [])

    def test_atomic_write_json_no_follow(self):
        target = self.root / "victim.json"
        target.write_text("keep")
        link = self.run_dir / "l.json"
        link.symlink_to(target)
        with self.assertRaises(FileExistsError):
            dispatch._atomic_write_json(link, {"a": 1})
        self.assertEqual(target.read_text(), "keep")

    # --- exit codes ---------------------------------------------------------------
    def test_exit_codes(self):
        self.assertEqual(self._serve(done=False, idle=0)[0], 2)          # bad idle timeout
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(dispatch.serve(self.root / "missing"), 2)
        self.assertEqual(self._serve()[0], 2)                            # no run.json
        self._manifest()
        spec = self._spec()
        spec["fan_out"] = {"width": 1}
        (self.run_dir / "run.json").write_text(json.dumps(spec))
        self.assertEqual(self._serve()[0], 2)
        self._manifest(models=("gpt-x",))
        self.assertEqual(self._serve()[0], 2)
        self._manifest()
        (self.inbox / "lead.done").unlink()
        rc, _ = self._serve(done=False, idle=0.05)
        self.assertEqual(rc, 0)
        self.assertEqual(self._spec()["broker"]["stop"], "idle-timeout")

    def test_exception_in_dispatch_does_not_stop_broker(self):
        self._manifest(total=3)
        self._request("e1")
        self._request("e2")
        calls = []

        def boom(kind, *a, **k):
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("x")
            return self._fake_launch()(kind, *a, **k)
        rc, _ = self._serve(launch=boom)
        self.assertEqual(rc, 0)
        self.assertEqual(self._result("e1")["status"], "red")
        self.assertEqual(self._result("e2")["status"], "green")

    # --- D51 hardening (sol review) -------------------------------------------------
    def test_inbox_missing_or_symlink_exit_2(self):
        self._manifest()
        self.inbox.rmdir()
        self.assertEqual(self._serve(done=False, idle=0.05)[0], 2)
        (self.run_dir / "inbox").symlink_to(self.root)
        self.assertEqual(self._serve(done=False, idle=0.05)[0], 2)

    def test_requests_outside_inbox_ignored(self):
        self._manifest()
        req = {"schema_version": 1, "request_id": "o1", "model": "haiku", "effort": "low", "tier": "grunt",
               "slots": self._slots()}
        (self.run_dir / "o1.request.json").write_text(json.dumps(req))
        self._serve()
        self.assertFalse((self.run_dir / "o1.result.json").exists())
        self.assertEqual(self.launches, [])

    def test_forged_result_never_read(self):
        self._manifest()
        forged = {"status": "green", "request_id": "r1", "dispatch_exit_code": 0}
        (self.inbox / "r1.result.json").write_text(json.dumps(forged))  # Lead's only write grant
        self._request("r1", slots={k: v for k, v in self._slots().items() if k != "OUT_OF_SCOPE"})
        self._serve()
        res = self._result("r1")
        self.assertEqual(res["dispatch_exit_code"], 3)  # broker's own verdict, not the forgery
        self.assertEqual(self._spec()["request_counts"]["duplicate"], 0)

    def test_worker_dir_symlink_refused_not_followed(self):
        self._manifest()
        outside = self.root / "outside"
        outside.mkdir()
        (self.run_dir / "workers").mkdir()
        (self.run_dir / "workers" / "r1").symlink_to(outside)
        self._request("r1")
        rc, _ = self._serve()
        self.assertEqual(rc, 0)
        self.assertEqual(self._result("r1")["reason"], "worker-dir-exists")
        self.assertEqual(list(outside.iterdir()), [])
        self.assertEqual(self.launches, [])

    def test_safe_writes_never_follow_symlink(self):
        target = self.root / "victim.txt"
        target.write_text("keep")
        link = self.run_dir / "stdout.md"
        link.symlink_to(target)
        dispatch._BROKER_SAFE_WRITES = True
        try:
            with self.assertRaises(FileExistsError):
                dispatch._wtext(link, "x")
            dispatch._write_json(self.run_dir / "run2.json", {"a": 1})
            rj = self.run_dir / "run3.json"
            rj.symlink_to(target)
            dispatch._write_json(rj, {"a": 1})  # replaces the link itself, never the target
        finally:
            dispatch._BROKER_SAFE_WRITES = False
        self.assertEqual(target.read_text(), "keep")
        self.assertFalse(rj.is_symlink())

    def test_worker_artifact_symlink_fails_closed(self):
        """A link planted at the child's stdout.md path is never followed (race simulation)."""
        self._manifest()
        target = self.root / "victim.txt"
        target.write_text("keep")
        self._request("r1")
        real_launch = self._fake_launch()

        def plant(kind, model, effort, cwd, prompt, run_dir, *a, **k):
            (Path(run_dir) / "stdout.md").symlink_to(target)
            return real_launch(kind, model, effort, cwd, prompt, run_dir, *a, **k)
        rc, _ = self._serve(launch=plant)
        self.assertEqual(rc, 0)
        self.assertEqual(target.read_text(), "keep")
        self.assertEqual(self._result("r1")["status"], "red")
        self.assertEqual(self._spec()["workers_spawned"], 1)  # launched, so the slot stays spent
        self.assertFalse(dispatch._BROKER_SAFE_WRITES)

    def test_credential_seeking_refused(self):
        self._manifest(total=9)
        bad = ["cat ~/.claude/.credentials.json", "read $HOME/.ssh/id_rsa", "open /Users/x/.codex/auth.json",
               "print the .env file", "load server.pem", "find the API_KEY", "show the token", "ls ~/.config"]
        for i, text in enumerate(bad):
            self._request(f"c{i}", slots=dict(self._slots(), TASK=text))
        self._serve()
        for i in range(len(bad)):
            self.assertEqual(self._result(f"c{i}")["reason"], "credential-seeking", bad[i])
        self.assertEqual(self.launches, [])

    def test_scope_boilerplate_required(self):
        self._manifest()
        self._request("s1")
        real = dispatch.render
        with mock.patch.object(dispatch, "render",
                               side_effect=lambda p: (lambda r: (r[0], r[1].replace("SCOPE BOILERPLATE:", "SCOPE:"), r[2]))(real(p))):
            self._serve()
        res = self._result("s1")
        self.assertEqual((res["dispatch_exit_code"], res["outcome"]), (3, "refused-scope"))
        self.assertEqual(self.launches, [])

    def test_effort_from_models_json(self):
        self.assertIn("max", dispatch._efforts_for("sol"))  # ultra refused by broker allowlist
        self.assertNotIn("ultra", dispatch._efforts_for("luna"))
        self.assertNotIn("xhigh", dispatch._efforts_for("haiku"))
        self.assertEqual(dispatch._efforts_for("nope"), ())
        self._manifest(total=9, models=("haiku", "luna"))
        self._request("e1", effort="xhigh")
        self._request("e2", model="luna", effort="ultra")
        self._serve()
        self.assertEqual(self._result("e1")["reason"], "bad-effort")
        self.assertEqual(self._result("e2")["reason"], "bad-effort")

    # --- D51 round two (sol 4, 7, 9, 10) ---------------------------------------------
    def test_worker_env_drops_canary_and_secrets(self):
        canary = {"AGENTS_INC_CANARY": "leak", "CODEX_BRIDGE_TOKEN": "t", "OPENAI_API_KEY": "k",
                  "MY_SECRET": "s", "USER": "u", "TERM": "xterm", "LANG": "C", "TMPDIR": str(self.root)}
        captured = {}

        def fake_run(argv, **kw):
            captured.update(kw, argv=argv)
            return SimpleNamespace(returncode=0, stdout=json.dumps({"result": "ok", "session_id": "s"}), stderr="")
        with mock.patch.dict("os.environ", canary), mock.patch.object(dispatch.subprocess, "run", side_effect=fake_run), \
                mock.patch.object(dispatch.shutil, "which", return_value="/opt/x/bin/claude"), \
                mock.patch.object(dispatch.os, "access", return_value=True):
            dispatch._BROKER_SAFE_WRITES = True
            try:
                dispatch.launch("claude", "haiku", "low", self.repo, "p", self.run_dir)
            finally:
                dispatch._BROKER_SAFE_WRITES = False
        env = captured["env"]
        self.assertEqual(set(env), {"PATH", "HOME", "USER", "TERM", "LANG", "TMPDIR"})
        for leaked in ("AGENTS_INC_CANARY", "CODEX_BRIDGE_TOKEN", "OPENAI_API_KEY", "MY_SECRET"):
            self.assertNotIn(leaked, env)
        self.assertNotIn("leak", json.dumps(env))
        self.assertEqual(env["PATH"], dispatch.WORKER_PATH + ":/opt/x/bin")
        self.assertEqual(env["TMPDIR"], str((self.run_dir / "tmp").resolve()))  # N3: child tmp, not inherited
        self.assertEqual(captured["argv"][:2], [dispatch.SANDBOX_EXEC, "-f"])
        prof = (self.run_dir / "sandbox.sb").read_text()
        self.assertIn(f'(require-not (subpath "{env["TMPDIR"]}"))', prof)

    def test_non_broker_launch_keeps_env(self):
        captured = {}
        with mock.patch.object(dispatch.subprocess, "run",
                               side_effect=lambda argv, **kw: captured.update(kw) or SimpleNamespace(
                                   returncode=0, stdout="{}", stderr="")):
            dispatch.launch("claude", "haiku", "low", self.repo, "p", self.run_dir)
        self.assertNotIn("env", captured)

    def test_sandbox_profile_denies_home_paths(self):
        prof = dispatch.claude_sandbox_profile(Path("/w"), Path("/h"), "/w/run/tmp")
        lines = prof.splitlines()
        for name in (".ssh", ".config", ".codex", ".codex-bridge", ".local", ".aws", ".gnupg", ".netrc"):
            self.assertIn(f'(subpath "/h/{name}")', lines[3], name)
        self.assertIn('(deny file-read* file-write* (regex #"^/h/\\.claude\\.json"))', lines[4])  # N1
        self.assertTrue(lines[5].startswith('(deny file-read* file-write* (require-all (subpath "/h/.claude")'))
        for name in dispatch.CLAUDE_HOME_ALLOW:
            self.assertIn(f'(require-not (subpath "/h/.claude/{name}"))', lines[5])
        self.assertIn('(require-not (subpath "/h/.claude/scripts"))', lines[5])   # hook scripts readable
        self.assertEqual(lines[6], '(deny file-write* (subpath "/h/.claude/scripts") (subpath "/h/.claude/settings.json"))')  # read only
        self.assertNotIn("settings.json", dispatch.CLAUDE_HOME_ALLOW)
        self.assertIn("settings.json", dispatch.CLAUDE_HOME_READ)
        self.assertIn('(require-not (subpath "/h/.claude/settings.json"))', lines[5])  # readable
        self.assertIn('(subpath "/h/.claude/settings.json")', lines[6])               # write-denied
        self.assertNotIn('(require-not (subpath "/h/.claude/.credentials.json"))', prof)
        scratch = f"/private/tmp/claude-{os.getuid()}"
        self.assertIn(f'(require-not (subpath "{scratch}"))', lines[2])         # Claude Code scratch grant
        self.assertNotIn('(subpath "/private/tmp")', prof)                     # N3: no bare /private/tmp
        self.assertNotIn('(require-not (subpath "/h/.claude"))', prof)          # no blanket ~/.claude write

    @unittest.skipUnless(os.access(dispatch.SANDBOX_EXEC, os.X_OK), "sandbox-exec unavailable")
    def test_sandbox_profile_enforced(self):
        home = self.root / "home"
        (home / ".ssh").mkdir(parents=True)
        (home / ".ssh" / "id_rsa").write_text("secret")
        (self.repo / "README.md").write_text("line one\n")
        prof = self.root / "p.sb"
        prof.write_text(dispatch.claude_sandbox_profile(self.repo, home, str(self.root / "t")))
        sb = [dispatch.SANDBOX_EXEC, "-f", str(prof)]
        denied = subprocess.run(sb + ["/bin/cat", str(home / ".ssh" / "id_rsa")], capture_output=True, text=True)
        if "sandbox_apply" in denied.stderr:
            self.skipTest("nested sandbox: " + denied.stderr.strip())
        self.assertNotEqual(denied.returncode, 0)
        self.assertNotIn("secret", denied.stdout)
        ok = subprocess.run(sb + ["/usr/bin/head", "-1", str(self.repo / "README.md")], capture_output=True, text=True)
        self.assertEqual(ok.stdout, "line one\n")
        wr = subprocess.run(sb + ["/usr/bin/touch", str(home / "outside")], capture_output=True, text=True)
        self.assertNotEqual(wr.returncode, 0)
        (home / ".claude" / "projects").mkdir(parents=True)
        (home / ".claude" / ".credentials.json").write_text("cred")
        (home / ".claude.json").write_text("cfg")
        for secret in (home / ".claude" / ".credentials.json", home / ".claude.json"):
            r = subprocess.run(sb + ["/bin/cat", str(secret)], capture_output=True, text=True)
            self.assertNotEqual(r.returncode, 0, secret)
        ok = subprocess.run(sb + ["/usr/bin/touch", str(home / ".claude" / "projects" / "t")], capture_output=True)
        self.assertEqual(ok.returncode, 0)
        (home / ".claude" / "scripts").mkdir()
        (home / ".claude" / "scripts" / "hook.py").write_text("hook\n")
        r = subprocess.run(sb + ["/bin/cat", str(home / ".claude" / "scripts" / "hook.py")], capture_output=True, text=True)
        self.assertEqual(r.stdout, "hook\n")
        r = subprocess.run(sb + ["/usr/bin/touch", str(home / ".claude" / "scripts" / "new")], capture_output=True)
        self.assertNotEqual(r.returncode, 0)
        (home / ".claude" / "settings.json").write_text("{}\n")
        r = subprocess.run(sb + ["/bin/cat", str(home / ".claude" / "settings.json")], capture_output=True, text=True)
        self.assertEqual(r.stdout, "{}\n")
        r = subprocess.run(sb + ["/usr/bin/touch", str(home / ".claude" / "settings.json")], capture_output=True)
        self.assertNotEqual(r.returncode, 0)
        r = subprocess.run(sb + ["/usr/bin/touch", "/private/tmp/n1probe"], capture_output=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse(Path("/private/tmp/n1probe").exists())
        scratch = Path(f"/private/tmp/claude-{os.getuid()}")
        scratch.mkdir(mode=0o700, exist_ok=True)
        probe = scratch / f"probe-{uuid.uuid4().hex}"
        try:
            r = subprocess.run(sb + ["/usr/bin/touch", str(probe)], capture_output=True)
            self.assertEqual(r.returncode, 0, r.stderr)
        finally:
            probe.unlink(missing_ok=True)

    def test_effort_ultra_refused(self):
        for model in ("sol", "haiku"):
            self.assertNotIn("ultra", dispatch._efforts_for(model), model)
            self.assertNotIn("xhigh", dispatch._efforts_for(model), model)
            self.assertTrue(set(dispatch._efforts_for(model)) <= set(dispatch.BROKER_EFFORTS), model)

    def test_no_sandbox_backend_refused(self):
        self._manifest(total=2)
        self._request("n1")
        with mock.patch.object(dispatch, "sandbox_available", return_value=False):
            self._serve()
        res = self._result("n1")
        self.assertEqual((res["status"], res["dispatch_exit_code"], res["reason"]), ("refused", 3, "no-sandbox-backend"))
        self.assertEqual(self.launches, [])

    def test_launch_refuses_unconfined_claude(self):
        with mock.patch.object(dispatch, "sandbox_available", return_value=False), \
                mock.patch.object(dispatch.subprocess, "run") as sp:
            dispatch._BROKER_SAFE_WRITES = True
            try:
                with self.assertRaises(RuntimeError):
                    dispatch.launch("claude", "haiku", "low", self.repo, "p", self.run_dir)
            finally:
                dispatch._BROKER_SAFE_WRITES = False
        sp.assert_not_called()

    def test_codex_broker_child_env_scrubbed(self):
        from agents_inc.install import runtime
        captured = {}
        receipt = SimpleNamespace(codex_path="/opt/x/bin/codex")
        paths = SimpleNamespace(receipt=self.root / "r.json", current=self.root)

        def fake_run_codex(*a, **kw):
            captured.update(kw)
            return 0
        with mock.patch.dict("os.environ", {"AGENTS_INC_CANARY": "leak", "CODEX_BRIDGE_TOKEN": "t"}), \
                mock.patch.object(cli, "_paths", return_value=paths), mock.patch.object(cli, "_efforts", return_value={}), \
                mock.patch("agents_inc.install.receipt.InstallReceipt.load", return_value=receipt), \
                mock.patch.object(runtime, "run_codex", side_effect=fake_run_codex):
            dispatch._BROKER_SAFE_WRITES = True
            try:
                dispatch.launch("codex", "sol", "high", self.repo, "p", self.run_dir)
            finally:
                dispatch._BROKER_SAFE_WRITES = False
        env = captured["env"]
        self.assertNotIn("AGENTS_INC_CANARY", env)
        self.assertNotIn("CODEX_BRIDGE_TOKEN", env)
        self.assertEqual(env["TMPDIR"], str((self.run_dir / "tmp").resolve()))
        self.assertIn(":/opt/x/bin", env["PATH"])

    def test_run_codex_passes_env(self):
        from agents_inc.install import runtime
        done = SimpleNamespace(stdout="OK\n", stderr="", returncode=0)
        m = {"sol": "gpt-5.6-sol"}
        for env in (None, {"PATH": "/usr/bin"}):
            with mock.patch.object(runtime, "load_model_map", return_value=m), \
                    mock.patch.object(runtime.subprocess, "run", return_value=done) as sp, \
                    mock.patch.object(runtime.os, "access", return_value=True), \
                    mock.patch.object(runtime.Path, "is_file", return_value=True), \
                    contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                runtime.run_codex("sol", "medium", self.repo, io.StringIO("p"), SimpleNamespace(codex_path="/x/codex"),
                                  {"gpt-5.6-sol": ["medium"]}, no_tools=True, env=env)
            self.assertEqual(sp.call_args.kwargs["env"], env)

    def test_child_usage_error_is_status_2(self):
        self._manifest(total=2)
        self._request("u1")
        self._serve(launch=self._fake_launch(rc=2))
        res = self._result("u1")
        self.assertEqual((res["status"], res["dispatch_exit_code"]), ("usage-error", 2))
        self.assertEqual(self._spec()["request_counts"]["usage-error"], 1)
        self.assertEqual(self._spec()["workers_spawned"], 1)

    def test_wait_found_and_timeout(self):
        t = [0.0]
        sleeps = []

        def sleep(n):
            sleeps.append(n)
            t[0] += n
            if t[0] >= 3:
                (self.run_dir / "w1.result.json").write_text("{}")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = dispatch.wait(self.run_dir, "w1", timeout=10, sleep=sleep, clock=lambda: t[0])
        self.assertEqual(rc, 0)
        self.assertEqual(out.getvalue().strip(), str(self.run_dir / "w1.result.json"))
        self.assertEqual(sleeps, [1, 1, 1])
        t[0] = 0.0
        with contextlib.redirect_stderr(io.StringIO()):
            rc = dispatch.wait(self.run_dir, "w2", timeout=5, sleep=lambda n: t.__setitem__(0, t[0] + n),
                               clock=lambda: t[0])
            self.assertEqual(rc, 124)
            self.assertEqual(dispatch.wait(self.run_dir, "../x", timeout=5), 2)

    def test_cli_routes_wait(self):
        with mock.patch.object(dispatch, "wait", return_value=124) as w:
            rc = cli.main(["dispatch", "--wait", "/r", "id1", "--timeout", "7"])
        self.assertEqual(rc, 124)
        w.assert_called_once_with("/r", "id1", 7.0)

    # --- CLI -----------------------------------------------------------------------
    def test_cli_routes_serve(self):
        with mock.patch.object(dispatch, "serve", return_value=0) as serve, \
                mock.patch.object(dispatch, "run") as run:
            rc = cli.main(["dispatch", "--serve", "/r", "--poll-interval", "0.5", "--idle-timeout", "9"])
        self.assertEqual(rc, 0)
        serve.assert_called_once_with("/r", 0.5, 9.0, None)
        run.assert_not_called()

    def test_cli_run_threads_run_dir(self):
        receipt = self.root / "receipt.json"
        receipt.write_text("{}")
        paths = SimpleNamespace(receipt=receipt, current=self.root)
        with mock.patch.object(cli, "_paths", return_value=paths), \
                mock.patch.object(cli.InstallReceipt, "load", return_value=SimpleNamespace(codex_path=None)), \
                mock.patch.object(cli, "_efforts", return_value={}), \
                mock.patch.object(cli, "run_codex", return_value=0) as rc_mock:
            cli.main(["run", "--model", "sol", "--cwd", str(self.repo), "--write", "--run-dir", str(self.run_dir)])
        self.assertEqual(rc_mock.call_args.args[-1], self.run_dir.resolve())
        with mock.patch.object(cli, "_paths", return_value=paths), \
                mock.patch.object(cli.InstallReceipt, "load", return_value=SimpleNamespace(codex_path=None)), \
                mock.patch.object(cli, "_efforts", return_value={}), \
                mock.patch.object(cli, "run_codex", return_value=0) as rc_mock:
            cli.main(["run", "--model", "sol", "--cwd", str(self.repo), "--write"])
        self.assertIsNone(rc_mock.call_args.args[-1])


if __name__ == "__main__":
    unittest.main()
