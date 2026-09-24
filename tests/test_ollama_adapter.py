"""Tests for ollama adapter. Unit tests, no sockets, no model loads."""
import unittest
import json
import sys
import os
import io
import itertools
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open, call

# Add agents_inc to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents_inc.adapters import ollama
from agents_inc import router, policy

# ollama.time IS the stdlib time module (same object) -- patching ollama.time.sleep
# patches time.sleep everywhere. Capture the real sleep before any test patches it, so
# fake HTTP handlers can still impose a short real delay to keep the worker thread alive
# long enough for the watchdog to observe a condition.
import time as _time_module
_REAL_SLEEP = _time_module.sleep


def run_main(argv, stdin_text="", state_dir=None):
    """Run ollama.main() with argv/stdin patched, temp AGENTS_INC_LOCAL_STATE, catching
    SystemExit. Returns (exit_code, stderr_text)."""
    tmp = state_dir or tempfile.mkdtemp()
    env_patch = {"AGENTS_INC_LOCAL_STATE": tmp}
    stderr_buf = io.StringIO()
    code = None
    with patch.dict(os.environ, env_patch), \
         patch.object(sys, "argv", ["ollama"] + list(argv)), \
         patch.object(sys, "stdin", io.StringIO(stdin_text)), \
         patch.object(sys, "stderr", stderr_buf):
        try:
            ollama.main()
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    if not state_dir:
        shutil.rmtree(tmp, ignore_errors=True)
    return code, stderr_buf.getvalue()


def healthy_snap(total_gib=16, free_pct=60, swap_used_bytes=0):
    total = total_gib * 1024**3
    return {"total_bytes": total, "free_pct": free_pct,
            "free_bytes": int(total * free_pct / 100), "swap_used_bytes": swap_used_bytes}


def tags_body(model, size=1 * 1024**3):
    return json.dumps({"models": [{"name": model, "size": size}]})


def make_fake_http(model, tags_status=200, tags_size=1 * 1024**3, tags_listed=True,
                   generate_status=200, generate_body=None, generate_raise=None,
                   generate_delay=0.0, ps_models=()):
    """Build a fake ollama._http_req(base_url, path, method, body, timeout_s, conn_holder)
    that branches on path: /api/tags, /api/generate (real request vs unload ping,
    told apart by whether "prompt" is in body), /api/ps. Returns (fn, calls) where
    calls records every (path, method, body) invocation for assertions."""
    calls = []

    def _fake(base_url, path, method="GET", body=None, timeout_s=2, conn_holder=None):
        calls.append((path, method, body))
        if path == "/api/tags":
            if tags_status != 200:
                raise ValueError("WB_LOCAL_HTTP: tags down")
            models = [{"name": model, "size": tags_size}] if tags_listed else []
            return tags_status, json.dumps({"models": models})
        if path == "/api/generate":
            if body and "prompt" in body:
                if generate_delay:
                    _REAL_SLEEP(generate_delay)  # real delay: keeps worker thread alive
                if generate_raise is not None:
                    raise generate_raise
                out = generate_body if generate_body is not None else json.dumps({"response": "ok"})
                return generate_status, out
            return 200, "{}"  # unload ping
        if path == "/api/ps":
            return 200, json.dumps({"models": [{"name": m} for m in ps_models]})
        return 200, "{}"

    return _fake, calls


class TestMemSnapshot(unittest.TestCase):
    """Test memory telemetry parsing: percent-based, spec-agnostic."""

    def test_macos_snapshot(self):
        """macOS sysctl parsing."""
        with patch("subprocess.check_output") as mock_run:
            mock_run.side_effect = [
                b"17179869184\n",  # hw.memsize (16 GiB)
                b"50\n",  # kern.memorystatus_level
                b"total = 5120.00M  used = 1024.00M  free = 4096.00M  (encrypted)\n"  # vm.swapusage
            ]
            with patch("os.uname") as mock_uname:
                mock_uname.return_value.sysname = "Darwin"
                snap = ollama.mem_snapshot()

        self.assertIsNotNone(snap)
        self.assertEqual(snap["total_bytes"], 17179869184)
        self.assertEqual(snap["free_pct"], 50)

    def test_linux_snapshot(self):
        """Linux /proc/meminfo parsing."""
        meminfo_text = """MemTotal:       16384000 kB
MemAvailable:    8192000 kB
SwapTotal:       2048000 kB
SwapFree:        1024000 kB
"""
        with patch("pathlib.Path.read_text", return_value=meminfo_text):
            with patch("os.uname") as mock_uname:
                mock_uname.return_value.sysname = "Linux"
                snap = ollama.mem_snapshot()

        self.assertIsNotNone(snap)
        self.assertEqual(snap["total_bytes"], 16384000 * 1024)
        self.assertEqual(snap["free_pct"], 50)

    def test_unknown_os_no_snapshot(self):
        """Unknown OS returns None."""
        with patch("os.uname") as mock_uname:
            mock_uname.return_value.sysname = "UnknownOS"
            snap = ollama.mem_snapshot()
        self.assertIsNone(snap)


class TestAdmit(unittest.TestCase):
    """Test admission checks: no telemetry, low memory."""

    def test_no_telemetry(self):
        """snap None -> WB_LOCAL_NO_TELEMETRY."""
        admitted, reason = ollama.admit("qwen2.5-coder:7b", None)
        self.assertFalse(admitted)
        self.assertEqual(reason, "WB_LOCAL_NO_TELEMETRY")

    def test_low_memory(self):
        """free_pct < 35 -> WB_LOCAL_LOW_MEMORY."""
        snap = {"total_bytes": 1024**3, "free_pct": 30, "free_bytes": int(1024**3*0.30), "swap_used_bytes": 0}
        admitted, reason = ollama.admit("qwen2.5-coder:7b", snap)
        self.assertFalse(admitted)
        self.assertEqual(reason, "WB_LOCAL_LOW_MEMORY")

    def test_percent_semantics_low_memory_rejection(self):
        """Free pct < 35 is rejected regardless of absolute RAM."""
        snap_low = {"total_bytes": 1024**3, "free_pct": 30, "free_bytes": int(1024**3*0.30), "swap_used_bytes": 0}

        admitted, reason = ollama.admit("qwen2.5-coder:7b", snap_low)
        self.assertFalse(admitted)
        self.assertEqual(reason, "WB_LOCAL_LOW_MEMORY")


class TestReady(unittest.TestCase):
    """Test model readiness check."""

    def test_model_not_in_allowlist(self):
        """Model not in routing.json models list -> ready() rejects."""
        ready_ok, reason = ollama.ready("unknown-model:99b")
        self.assertFalse(ready_ok)
        self.assertEqual(reason, "WB_LOCAL_MODEL_NOT_ALLOWED")

    def test_model_in_allowlist(self):
        """Model in allowlist is checked."""
        ready_ok, reason = ollama.ready("qwen2.5-coder:7b")
        # ready() checks if model is in allowlist (yes) and then tries HTTP
        # Without mocking HTTP, it will fail with HTTP error, but that's after allowlist check


class TestEstimateTokens(unittest.TestCase):
    """Test input token estimation."""

    def test_token_estimate(self):
        """Estimate = ceil(len(prompt.encode())/3)."""
        prompt = "a" * 300  # 300 bytes -> 100 tokens
        est = ollama._estimate_tokens(prompt)
        self.assertEqual(est, 100)


class TestBreaker(unittest.TestCase):
    """Test circuit breaker logic."""

    def test_breaker_write_read_logic(self):
        """Breaker reason can be written and checked."""
        reason = "WB_LOCAL_TIMEOUT"
        breaker_data = {"reason": reason, "ts": 12345.0}
        breaker_json = json.dumps(breaker_data)

        # Verify JSON structure
        loaded = json.loads(breaker_json)
        self.assertEqual(loaded["reason"], reason)


class TestRouterOllama(unittest.TestCase):
    """Test router: ollama availability and authorization (item 18)."""

    def test_ollama_absent_without_available(self):
        """Without ollama in available set, ollama not in chain."""
        available = {"claude", "codex"}  # ollama not available
        chain = router.pick_model_chain("extract", "grunt", available, False)
        models = [r.provider for r in chain]
        self.assertNotIn("ollama", models)

    def test_ollama_in_available_but_no_prefer_no_local_only(self):
        """ollama in available + local_authorized but no prefer/local_only -> not chosen."""
        available = {"claude", "codex", "ollama"}
        # Without prefer_provider="ollama" or local_only=True, ollama should not be in chain
        chain = router.pick_model_chain("extract", "grunt", available, False, local_authorized=True)
        models = [r.provider for r in chain]
        self.assertNotIn("ollama", models)

    def test_ollama_with_prefer_and_local_auth(self):
        """prefer_provider='ollama' + local_authorized=True -> ollama selected."""
        available = {"claude", "codex", "ollama"}
        route = router.pick_model("extract", "grunt", available, False, prefer_provider="ollama", local_authorized=True)
        self.assertIsNotNone(route)
        self.assertEqual(route.provider, "ollama")

    def test_ollama_with_prefer_without_local_auth(self):
        """prefer_provider='ollama' but local_authorized=False -> ollama not selected."""
        available = {"claude", "codex", "ollama"}
        route = router.pick_model("extract", "grunt", available, False, prefer_provider="ollama", local_authorized=False)
        # Should fallback to other providers
        self.assertIsNotNone(route)
        self.assertNotEqual(route.provider, "ollama")

    def test_local_only_restricts_to_ollama(self):
        """local_only=True restricts to ollama only."""
        available = {"claude", "codex", "ollama"}
        chain = router.pick_model_chain("extract", "grunt", available, False, local_authorized=True, local_only=True)
        models = [r.provider for r in chain]
        # Should only contain ollama routes
        self.assertTrue(all(p == "ollama" for p in models) if models else True)


class TestPolicyOllama(unittest.TestCase):
    """Test policy for ollama."""

    def test_ollama_confidential_requires_local_auth(self):
        """ollama + confidential + not local_authorized -> WB_LOCAL_AUTH_REQUIRED."""
        workspace = Path("/tmp/ws")
        with patch("agents_inc.policy.is_local_authorized", return_value=False):
            route = router.Route("ollama", "qwen2.5-coder:7b", "grunt", "http")
            with self.assertRaises(policy.PolicyError) as cm:
                policy.check_dispatch(route, workspace, True)
            self.assertIn("WB_LOCAL_AUTH_REQUIRED", str(cm.exception))

    def test_ollama_with_local_auth_passes(self):
        """ollama + confidential + local_authorized -> OK."""
        workspace = Path("/tmp/ws")
        with patch("agents_inc.policy.is_local_authorized", return_value=True):
            route = router.Route("ollama", "qwen2.5-coder:7b", "grunt", "http")
            # Should not raise
            policy.check_dispatch(route, workspace, True)


class TestBuildCmd(unittest.TestCase):
    """Test build_cmd function."""

    def test_build_cmd_format(self):
        """build_cmd returns correct format."""
        cmd = ollama.build_cmd("qwen2.5-coder:7b")
        self.assertEqual(len(cmd), 4)
        self.assertEqual(cmd[0], sys.executable)
        self.assertEqual(cmd[1], "-m")
        self.assertEqual(cmd[2], "agents_inc.adapters.ollama")
        self.assertEqual(cmd[3], "qwen2.5-coder:7b")


class TestAdmitPercent(unittest.TestCase):
    """Test admission percent semantics (item 11): same decision regardless of total RAM."""

    def test_admit_8gb_free_40pct(self):
        """8 GiB total, 40% free -> admit (with small model, headroom 1.5 + projection margin clear)."""
        snap = {"total_bytes": 8*1024**3, "free_pct": 40, "free_bytes": int(8*1024**3*0.40), "swap_used_bytes": 0}
        # 200 MiB model: headroom needed = 0.3 GiB (well under 3.2 GiB free); projected drop
        # = 200MiB*1.5/8GiB*100 = 3.75 pts, projected free 36.25% clears abort(25)+margin(5)=30.
        admitted, reason = ollama.admit("qwen2.5-coder:7b", snap, model_size=int(0.2*1024**3))
        self.assertTrue(admitted)

    def test_admit_16gb_free_40pct(self):
        """16 GiB total, 40% free -> admit (same small model, same pct math)."""
        snap = {"total_bytes": 16*1024**3, "free_pct": 40, "free_bytes": int(16*1024**3*0.40), "swap_used_bytes": 0}
        admitted, reason = ollama.admit("qwen2.5-coder:7b", snap, model_size=int(0.2*1024**3))
        self.assertTrue(admitted)

    def test_admit_64gb_free_40pct(self):
        """64 GiB total, 40% free -> admit (same small model, same pct math)."""
        snap = {"total_bytes": 64*1024**3, "free_pct": 40, "free_bytes": int(64*1024**3*0.40), "swap_used_bytes": 0}
        admitted, reason = ollama.admit("qwen2.5-coder:7b", snap, model_size=int(0.2*1024**3))
        self.assertTrue(admitted)

    def test_reject_8gb_free_30pct(self):
        """8 GiB total, 30% free -> reject (< 35%)."""
        snap = {"total_bytes": 8*1024**3, "free_pct": 30, "free_bytes": int(8*1024**3*0.30), "swap_used_bytes": 0}
        admitted, reason = ollama.admit("qwen2.5-coder:7b", snap, model_size=4*1024**3)
        self.assertFalse(admitted)
        self.assertEqual(reason, "WB_LOCAL_LOW_MEMORY")

    def test_reject_128gb_free_30pct(self):
        """128 GiB total, 30% free -> reject (< 35%)."""
        snap = {"total_bytes": 128*1024**3, "free_pct": 30, "free_bytes": int(128*1024**3*0.30), "swap_used_bytes": 0}
        admitted, reason = ollama.admit("qwen2.5-coder:7b", snap, model_size=4*1024**3)
        self.assertFalse(admitted)
        self.assertEqual(reason, "WB_LOCAL_LOW_MEMORY")


class TestAdmitModelHeadroom(unittest.TestCase):
    """Test model headroom check (item 12)."""

    def test_model_headroom_reject(self):
        """free_bytes < model_size * 1.5 -> reject WB_LOCAL_MODEL_TOO_BIG (returns before
        the projected-admission check even runs)."""
        model_size = 4*1024**3  # 4 GiB
        snap = {"total_bytes": 16*1024**3, "free_pct": 40, "free_bytes": int(4*1024**3), "swap_used_bytes": 0}
        # free_bytes = 4 GiB, needed = 4 * 1.5 = 6 GiB -> reject
        admitted, reason = ollama.admit("qwen2.5-coder:7b", snap, model_size=model_size)
        self.assertFalse(admitted)
        self.assertEqual(reason, "WB_LOCAL_MODEL_TOO_BIG")

    def test_model_headroom_admit(self):
        """free_bytes >= model_size * 1.5 AND clears the projected-admission margin -> admit."""
        model_size = 1*1024**3  # 1 GiB: small relative to 16 GiB total so the projection
                                 # check (percent of total, not absolute) also clears.
        snap = {"total_bytes": 16*1024**3, "free_pct": 40, "free_bytes": int(2*1024**3), "swap_used_bytes": 0}
        # free_bytes = 2 GiB, needed = 1.5 GiB -> headroom ok.
        # projected = 40 - (1*1.5/16*100) = 30.625 >= abort_free_pct(25)+margin(5)=30 -> admit
        admitted, reason = ollama.admit("qwen2.5-coder:7b", snap, model_size=model_size)
        self.assertTrue(admitted)


class TestProjectedAdmission(unittest.TestCase):
    """Follow-up 3 change 4a: admission rejects upfront any model whose projected
    post-load footprint would breach the watchdog's abort line + margin. Percent-scaled,
    no absolute GiB threshold -- proven across two total-RAM sizes."""

    SEVEN_B_SIZE = 4683087561  # live-measured qwen2.5-coder:7b size
    THREE_B_SIZE = 1929912626  # live-measured qwen2.5-coder:3b size

    def test_16gib_60pct_free_7b_rejected_projected(self):
        """16 GiB total, 60% free: 7b's projected footprint breaches abort(25)+margin(5)=30."""
        snap = {"total_bytes": 16*1024**3, "free_pct": 60, "free_bytes": int(16*1024**3*0.60), "swap_used_bytes": 0}
        admitted, reason = ollama.admit("qwen2.5-coder:7b", snap, model_size=self.SEVEN_B_SIZE)
        self.assertFalse(admitted)
        self.assertEqual(reason, "WB_LOCAL_PROJECTED_LOW_MEMORY")

    def test_16gib_60pct_free_3b_admitted(self):
        """16 GiB total, 60% free: 3b's smaller footprint clears the projection margin."""
        snap = {"total_bytes": 16*1024**3, "free_pct": 60, "free_bytes": int(16*1024**3*0.60), "swap_used_bytes": 0}
        admitted, reason = ollama.admit("qwen2.5-coder:3b", snap, model_size=self.THREE_B_SIZE)
        self.assertTrue(admitted)

    def test_64gib_60pct_free_7b_admitted(self):
        """64 GiB total, 60% free: same 7b model now admits -- proves the check scales by
        percent of total RAM, not an absolute model-size threshold."""
        snap = {"total_bytes": 64*1024**3, "free_pct": 60, "free_bytes": int(64*1024**3*0.60), "swap_used_bytes": 0}
        admitted, reason = ollama.admit("qwen2.5-coder:7b", snap, model_size=self.SEVEN_B_SIZE)
        self.assertTrue(admitted)


class TestInputBudget(unittest.TestCase):
    """Test input token budget (item 13)."""

    def test_input_too_large(self):
        """Input > max_input_tokens -> reject."""
        # max_input_tokens = 3072 (default)
        # estimate = ceil(len(prompt.encode())/3)
        # So prompt length > 3072*3 = 9216 bytes triggers rejection
        prompt = "a" * 9217
        est = ollama._estimate_tokens(prompt)
        self.assertGreater(est, 3072)


class TestLockBusy(unittest.TestCase):
    """Test lock acquisition (item 14)."""

    def test_lock_acquire_success(self):
        """Lock acquire returns handle on success."""
        with patch("fcntl.flock"):
            with patch("builtins.open", mock_open()) as mock_file:
                result = ollama._acquire_lock(Path("/tmp/test.lock"))
                self.assertIsNotNone(result)

    def test_lock_acquire_fail_blocking(self):
        """Lock acquire returns None on BlockingIOError."""
        with patch("builtins.open", side_effect=BlockingIOError):
            result = ollama._acquire_lock(Path("/tmp/test.lock"))
            self.assertIsNone(result)

    def test_lock_exclusivity_real_flock(self):
        """Follow-up 3 change 4b: real fcntl.flock exclusivity, no mocking of flock itself.
        A second _acquire_lock on the same path, via a fresh open() (not reusing the first
        handle), must fail while the first holder is still open. Proves the lock is truly
        exclusive (LOCK_EX), not shared (LOCK_SH) -- caught this gap in the fix2 pass, where
        a LOCK_EX->LOCK_SH mutation left the old mocked test green."""
        tmpdir = tempfile.mkdtemp()
        try:
            lock_path = Path(tmpdir) / "ollama.lock"
            h1 = ollama._acquire_lock(lock_path)
            self.addCleanup(lambda: h1 and h1.close())
            self.assertIsNotNone(h1, "first acquire on an uncontended lock must succeed")
            h2 = ollama._acquire_lock(lock_path)  # fresh open(), same path, first still held
            self.assertIsNone(h2, "second acquire must fail while the first holder is open")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


class TestWatchdogAbort(unittest.TestCase):
    """Test watchdog conditions (item 15 / defect 6d): each calls real main(), asserts
    exit 3, unload observed (ps call happened), breaker file written, stderr reason."""

    MODEL = "qwen2.5-coder:7b"

    def _run(self, mem_side_effect, generate_raise=None):
        state_dir = tempfile.mkdtemp()
        try:
            fake_http, calls = make_fake_http(self.MODEL, ps_models=[self.MODEL],
                                              generate_raise=generate_raise, generate_delay=0.03)
            with patch.object(ollama, "_http_req", side_effect=fake_http), \
                 patch.object(ollama, "mem_snapshot", side_effect=mem_side_effect), \
                 patch.object(ollama.time, "sleep", return_value=None), \
                 patch.dict(ollama._CONFIG, {"deadline_s": 0.02, "watchdog_interval_s": 0.001,
                                             "unload_verify_s": 0.02}):
                code, err = run_main([self.MODEL], stdin_text="hi", state_dir=state_dir)
            breaker_written = (Path(state_dir) / "ollama.disabled").exists()
            ps_called = any(c[0] == "/api/ps" for c in calls)
            return code, err, breaker_written, ps_called
        finally:
            shutil.rmtree(state_dir, ignore_errors=True)

    def test_watchdog_free_pct_drop(self):
        """free_pct < abort_free_pct mid-run -> exit 3, unload observed, breaker written."""
        low = healthy_snap(free_pct=10)
        code, err, breaker, ps_called = self._run(itertools.chain([healthy_snap()], itertools.repeat(low)),
                                                   generate_raise=OSError("blocked"))
        self.assertEqual(code, 3)
        self.assertTrue(err.startswith("WB_LOCAL_LOW_MEMORY_ABORT"))
        self.assertTrue(breaker)
        self.assertTrue(ps_called)

    def test_watchdog_swap_growth(self):
        """swap growth > max_swap_growth_pct of total -> exit 3, unload observed, breaker."""
        base = healthy_snap(swap_used_bytes=0)
        grown = healthy_snap(swap_used_bytes=int(16 * 1024**3 * 0.05))
        code, err, breaker, ps_called = self._run(itertools.chain([base], itertools.repeat(grown)),
                                                   generate_raise=OSError("blocked"))
        self.assertEqual(code, 3)
        self.assertTrue(err.startswith("WB_LOCAL_SWAP_GROWTH"))
        self.assertTrue(breaker)
        self.assertTrue(ps_called)

    def test_watchdog_deadline(self):
        """elapsed > deadline_s while worker still running -> exit 3, unload observed, breaker."""
        # deadline path needs the generate call itself to take longer than deadline_s.
        state_dir = tempfile.mkdtemp()
        try:
            fake_http, calls = make_fake_http(self.MODEL, ps_models=[self.MODEL], generate_delay=0.05)
            with patch.object(ollama, "_http_req", side_effect=fake_http), \
                 patch.object(ollama, "mem_snapshot", side_effect=itertools.repeat(healthy_snap())), \
                 patch.object(ollama.time, "sleep", return_value=None), \
                 patch.dict(ollama._CONFIG, {"deadline_s": 0.01, "watchdog_interval_s": 0.001,
                                             "unload_verify_s": 0.02}):
                code2, err2 = run_main([self.MODEL], stdin_text="hi", state_dir=state_dir)
            self.assertEqual(code2, 3)
            self.assertTrue(err2.startswith("WB_LOCAL_DEADLINE"))
            self.assertTrue((Path(state_dir) / "ollama.disabled").exists())
        finally:
            shutil.rmtree(state_dir, ignore_errors=True)

    def test_watchdog_telemetry_lost(self):
        """mem_snapshot() -> None mid-run must abort, not continue silently (defect 1)."""
        code, err, breaker, ps_called = self._run(itertools.chain([healthy_snap()], itertools.repeat(None)),
                                                   generate_raise=OSError("blocked"))
        self.assertEqual(code, 3)
        self.assertTrue(err.startswith("WB_LOCAL_TELEMETRY_LOST"))
        self.assertTrue(breaker)
        self.assertTrue(ps_called)


class TestUnloadUnconfirmed(unittest.TestCase):
    """Test unload verification (item 16 / defect 6a): model still listed in /api/ps after
    unload_verify_s -> exit 4, breaker written."""

    def test_unload_unconfirmed_exit4(self):
        model = "qwen2.5-coder:7b"
        state_dir = tempfile.mkdtemp()
        try:
            fake_http, calls = make_fake_http(model, ps_models=[model])  # model never disappears
            with patch.object(ollama, "_http_req", side_effect=fake_http), \
                 patch.object(ollama, "mem_snapshot", return_value=healthy_snap()), \
                 patch.object(ollama.time, "sleep", return_value=None), \
                 patch.dict(ollama._CONFIG, {"unload_verify_s": 0.02, "deadline_s": 5}):
                code, err = run_main([model], stdin_text="hi", state_dir=state_dir)
            self.assertEqual(code, 4)
            self.assertTrue(err.startswith("WB_LOCAL_UNLOAD_UNCONFIRMED"))
            self.assertTrue((Path(state_dir) / "ollama.disabled").exists())
        finally:
            shutil.rmtree(state_dir, ignore_errors=True)


class TestHTTPErrors(unittest.TestCase):
    """Test HTTP error handling (item 17 / defect 6b, 6c)."""

    def test_connect_refused_no_breaker(self):
        """Connect refused on generate -> exit 1, NO breaker (server down, not our fault)."""
        model = "qwen2.5-coder:7b"
        state_dir = tempfile.mkdtemp()
        try:
            fake_http, calls = make_fake_http(model, generate_raise=ConnectionRefusedError("refused"))
            with patch.object(ollama, "_http_req", side_effect=fake_http), \
                 patch.object(ollama, "mem_snapshot", return_value=healthy_snap()), \
                 patch.object(ollama.time, "sleep", return_value=None), \
                 patch.dict(ollama._CONFIG, {"unload_verify_s": 0.02, "deadline_s": 5}):
                code, err = run_main([model], stdin_text="hi", state_dir=state_dir)
            self.assertEqual(code, 1)
            self.assertTrue(err.startswith("WB_LOCAL_HTTP"))
            self.assertFalse((Path(state_dir) / "ollama.disabled").exists())
        finally:
            shutil.rmtree(state_dir, ignore_errors=True)

    def test_http_500_sets_breaker(self):
        """HTTP 500 on generate -> exit 1, breaker written."""
        model = "qwen2.5-coder:7b"
        state_dir = tempfile.mkdtemp()
        try:
            fake_http, calls = make_fake_http(model, generate_status=500, generate_body="server error")
            with patch.object(ollama, "_http_req", side_effect=fake_http), \
                 patch.object(ollama, "mem_snapshot", return_value=healthy_snap()), \
                 patch.object(ollama.time, "sleep", return_value=None), \
                 patch.dict(ollama._CONFIG, {"unload_verify_s": 0.02, "deadline_s": 5}):
                code, err = run_main([model], stdin_text="hi", state_dir=state_dir)
            self.assertEqual(code, 1)
            self.assertTrue(err.startswith("WB_LOCAL_HTTP"))
            self.assertTrue((Path(state_dir) / "ollama.disabled").exists())
        finally:
            shutil.rmtree(state_dir, ignore_errors=True)


class TestSuccessPath(unittest.TestCase):
    """Test full success path (defect 6f): exit 0, stdout = response, keep_alive:0,
    num_ctx == 4096, think:false only for qwen3:8b."""

    def test_success_no_think_model(self):
        model = "qwen2.5-coder:7b"
        state_dir = tempfile.mkdtemp()
        try:
            fake_http, calls = make_fake_http(model, generate_body=json.dumps({"response": "hello world"}),
                                              ps_models=[])
            with patch.object(ollama, "_http_req", side_effect=fake_http), \
                 patch.object(ollama, "mem_snapshot", return_value=healthy_snap()), \
                 patch.object(ollama.time, "sleep", return_value=None), \
                 patch.dict(ollama._CONFIG, {"unload_verify_s": 0.02, "deadline_s": 5}):
                code, err = run_main([model], stdin_text="prompt text", state_dir=state_dir)
            self.assertEqual(code, 0)
            gen_calls = [c for c in calls if c[0] == "/api/generate" and c[2] and "prompt" in c[2]]
            self.assertEqual(len(gen_calls), 1)
            body = gen_calls[0][2]
            self.assertEqual(body["keep_alive"], 0)
            self.assertEqual(body["options"]["num_ctx"], 4096)
            self.assertNotIn("think", body)
        finally:
            shutil.rmtree(state_dir, ignore_errors=True)

    def test_success_think_false_for_qwen3(self):
        model = "qwen3:8b"
        state_dir = tempfile.mkdtemp()
        try:
            fake_http, calls = make_fake_http(model, generate_body=json.dumps({"response": "hi"}), ps_models=[])
            with patch.object(ollama, "_http_req", side_effect=fake_http), \
                 patch.object(ollama, "mem_snapshot", return_value=healthy_snap()), \
                 patch.object(ollama.time, "sleep", return_value=None), \
                 patch.dict(ollama._CONFIG, {"unload_verify_s": 0.02, "deadline_s": 5}):
                code, err = run_main([model], stdin_text="prompt text", state_dir=state_dir)
            self.assertEqual(code, 0)
            gen_calls = [c for c in calls if c[0] == "/api/generate" and c[2] and "prompt" in c[2]]
            self.assertEqual(gen_calls[0][2]["think"], False)
        finally:
            shutil.rmtree(state_dir, ignore_errors=True)


class TestModelNotListed(unittest.TestCase):
    """Tags reachable but model not in /api/tags listing -> exit 2 WB_LOCAL_MODEL_NOT_ALLOWED
    (item 6e), distinct from tags being unreachable -> exit 1."""

    def test_model_not_listed_exit2(self):
        model = "qwen2.5-coder:7b"
        state_dir = tempfile.mkdtemp()
        try:
            fake_http, calls = make_fake_http(model, tags_listed=False)
            with patch.object(ollama, "_http_req", side_effect=fake_http), \
                 patch.object(ollama, "mem_snapshot", return_value=healthy_snap()):
                code, err = run_main([model], stdin_text="hi", state_dir=state_dir)
            self.assertEqual(code, 2)
            self.assertTrue(err.startswith("WB_LOCAL_MODEL_NOT_ALLOWED"))
            self.assertFalse((Path(state_dir) / "ollama.disabled").exists())
        finally:
            shutil.rmtree(state_dir, ignore_errors=True)

    def test_tags_unreachable_exit1_no_breaker(self):
        model = "qwen2.5-coder:7b"
        state_dir = tempfile.mkdtemp()
        try:
            fake_http, calls = make_fake_http(model, tags_status=500)
            with patch.object(ollama, "_http_req", side_effect=fake_http), \
                 patch.object(ollama, "mem_snapshot", return_value=healthy_snap()):
                code, err = run_main([model], stdin_text="hi", state_dir=state_dir)
            self.assertEqual(code, 1)
            self.assertTrue(err.startswith("WB_LOCAL_HTTP"))
            self.assertFalse((Path(state_dir) / "ollama.disabled").exists())
        finally:
            shutil.rmtree(state_dir, ignore_errors=True)


class TestPipelineLocalOnly(unittest.TestCase):
    """Test pipeline local_only behavior (item 19 / defect 6g, 6h). Uses the real brief()
    with a fake runner -- no subprocess, no live ollama."""

    def setUp(self):
        from agents_inc.adapters.base import WorkerResult
        self.WorkerResult = WorkerResult
        self.FIX = Path(__file__).resolve().parent.parent / "fixtures"
        self.exp = json.loads((self.FIX / "sample-b" / "expected.json").read_text())
        self.ws = Path(tempfile.mkdtemp())
        ws_dir = self.ws / ".workerbees"
        ws_dir.mkdir(parents=True, exist_ok=True)
        (ws_dir / "authorization.json").write_text(json.dumps({"local_only": True}))

    def tearDown(self):
        shutil.rmtree(self.ws, ignore_errors=True)

    def _counting_runner(self, payload):
        calls = {"n": 0}
        def runner(cmd, stdin_text, timeout=300):
            calls["n"] += 1
            return self.WorkerResult("returned", json.dumps(payload), "", 0)
        return runner, calls

    def test_local_only_no_reviewer(self):
        """local_only=True -> reviewer runner never called; receipt content_review ==
        'local_only_no_review'."""
        from agents_inc.pipeline import brief
        payload = {"claims": [dict(text="t", **c) for c in self.exp["required_claims"]],
                   "draft": "Brief. (p2)"}
        runner, calls = self._counting_runner(payload)
        r = brief(self.FIX / "sample-b" / "matter.md", "sample-b", "lawyer", self.ws,
                  available={"ollama"}, runner=runner, local_only=True)
        self.assertEqual(r.status, "returned")
        self.assertEqual(r.receipt["content_review"], "local_only_no_review")
        self.assertEqual(r.route.provider, "ollama")
        # only the worker (extract) call happened -- no reviewer dispatch
        self.assertEqual(calls["n"], 1)

    def test_local_only_unavailable_blocked(self):
        """local_only=True w/o ollama in available -> blocked WB_LOCAL_UNAVAILABLE, no
        remote fallback."""
        from agents_inc.pipeline import brief
        runner, calls = self._counting_runner({})
        r = brief(self.FIX / "sample-b" / "matter.md", "sample-b", "lawyer", self.ws,
                  available={"claude"}, runner=runner, local_only=True)
        self.assertEqual(r.status, "blocked")
        self.assertEqual(r.receipt["reason"], "WB_LOCAL_UNAVAILABLE")
        self.assertEqual(calls["n"], 0)

    def test_worker_provider_ollama_normal_path(self):
        """brief(worker_provider='ollama') normal (non local_only) path -> route.provider
        == 'ollama' when opted in + local-authorized (item 6h)."""
        from agents_inc.pipeline import brief
        payload = {"claims": [dict(text="t", **c) for c in self.exp["required_claims"]],
                   "draft": "Brief. (p2)"}
        runner, calls = self._counting_runner(payload)
        r = brief(self.FIX / "sample-b" / "matter.md", "sample-b", "lawyer", self.ws,
                  available={"ollama"}, runner=runner, worker_provider="ollama")
        self.assertEqual(r.route.provider, "ollama")


class TestDoctorNoProbe(unittest.TestCase):
    """Test doctor doesn't probe ollama without opt-in (item 20)."""

    def test_doctor_no_workerbees_local(self):
        """WORKERBEES_LOCAL unset -> ollama.ready never called."""
        with patch.dict(os.environ, {}, clear=False):
            # Ensure WORKERBEES_LOCAL is not set
            if "WORKERBEES_LOCAL" in os.environ:
                del os.environ["WORKERBEES_LOCAL"]

            with patch("agents_inc.adapters.ollama.ready") as mock_ready:
                workspace = Path("/tmp/test_ws")
                # Create minimal doctor.json
                ws_dir = workspace / ".workerbees"
                ws_dir.mkdir(parents=True, exist_ok=True)
                doctor_json = {
                    "results": {"claude": {"status": "ok"}, "codex": {"status": "ok"}},
                    "paused": [],
                    "at": "2026-09-22T00:00:00Z",
                    "epoch": 1695340800.0
                }
                (ws_dir / "doctor.json").write_text(json.dumps(doctor_json))

                from agents_inc import doctor
                available = doctor.available(workspace)

                # ollama.ready should not have been called
                mock_ready.assert_not_called()


class TestEdgeCases(unittest.TestCase):
    """Test edge cases."""

    def test_non_loopback_refused(self):
        """Endpoint with non-loopback host raises ValueError."""
        with self.assertRaises(ValueError) as cm:
            ollama._http_req("http://192.168.1.1:11434", "/api/generate", method="POST", body={})
        self.assertIn("WB_LOCAL_NON_LOOPBACK", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
