"""Local ollama adapter. HTTP behind subprocess, stdlib only, percent-based memory guards."""
from __future__ import annotations
import sys, os, json, time, fcntl, threading, subprocess, math, re, http.client
from pathlib import Path
from dataclasses import dataclass

# Read config from routing.json
def _load_config() -> dict:
    try:
        routing = json.loads((Path(__file__).parent.parent / "routing.json").read_text())
        return routing.get("local", {})
    except Exception:
        return {}

def build_cmd(model: str) -> list[str]:
    """Return [sys.executable, "-m", "agents_inc.adapters.ollama", model]."""
    return [sys.executable, "-m", "agents_inc.adapters.ollama", model]

_CONFIG = _load_config()
_LOCK_HANDLE = None  # Module-level lock file handle, kept open for process lifetime

def _state_dir() -> Path:
    env_path = os.environ.get("AGENTS_INC_LOCAL_STATE")
    if env_path:
        return Path(env_path)
    return Path.home() / ".cache" / "agents-inc" / "local"

def _load_allowlist() -> list[str]:
    return _CONFIG.get("models", [])

def mem_snapshot() -> dict | None:
    """Return {total_bytes, free_pct, free_bytes, swap_used_bytes} or None on error."""
    uname = os.uname().sysname
    try:
        if uname == "Darwin":
            # macOS: sysctl calls
            import subprocess
            total_b = int(subprocess.check_output(["sysctl", "-n", "hw.memsize"]).decode().strip())
            free_pct = int(subprocess.check_output(["sysctl", "-n", "kern.memorystatus_level"]).decode().strip())
            swap_output = subprocess.check_output(["sysctl", "-n", "vm.swapusage"]).decode().strip()
            # Parse: "total = 5120.00M  used = 3394.75M  free = 1725.25M  (encrypted)"
            match = re.search(r"used\s*=\s*([\d.]+)\s*M", swap_output)
            swap_used_b = int(float(match.group(1)) * 1024 * 1024) if match else 0
            free_b = int(total_b * free_pct / 100)
            return {"total_bytes": total_b, "free_pct": free_pct, "free_bytes": free_b, "swap_used_bytes": swap_used_b}
        elif uname == "Linux":
            # Linux: /proc/meminfo (kB)
            meminfo = Path("/proc/meminfo").read_text()
            values = {}
            for line in meminfo.split("\n"):
                if not line.strip():
                    continue
                parts = line.split(":")
                if len(parts) == 2:
                    key = parts[0].strip()
                    val_str = parts[1].strip().split()[0]
                    try:
                        values[key] = int(val_str) * 1024  # Convert kB to bytes
                    except ValueError:
                        pass
            total_b = values.get("MemTotal", 0)
            available_b = values.get("MemAvailable", 0)
            swap_used_b = values.get("SwapTotal", 0) - values.get("SwapFree", 0)
            if total_b <= 0:
                return None
            free_pct = int(100 * available_b / total_b) if total_b > 0 else 0
            return {"total_bytes": total_b, "free_pct": free_pct, "free_bytes": available_b, "swap_used_bytes": swap_used_b}
        else:
            return None
    except Exception:
        return None

def ready(model: str, base_url: str | None = None, opener=None) -> tuple[bool, str]:
    """GET /api/tags timeout connect_timeout_s; model in allowlist AND listed."""
    if model not in _load_allowlist():
        return False, "WB_LOCAL_MODEL_NOT_ALLOWED"
    endpoint = base_url or _CONFIG.get("endpoint", "http://127.0.0.1:11434")
    timeout_s = _CONFIG.get("connect_timeout_s", 2)
    try:
        host, port = endpoint.replace("http://", "").replace("https://", "").split(":")
        port = int(port)
    except Exception:
        return False, "WB_LOCAL_ENDPOINT_INVALID"
    try:
        conn = http.client.HTTPConnection(host, port, timeout=timeout_s)
        conn.request("GET", "/api/tags")
        resp = conn.getresponse()
        body = resp.read().decode()
        conn.close()
        if resp.status != 200:
            return False, "WB_LOCAL_HTTP"
        data = json.loads(body)
        models = [m.get("name") for m in data.get("models", [])]
        return model in models, "" if model in models else "WB_LOCAL_MODEL_NOT_READY"
    except Exception as e:
        return False, f"WB_LOCAL_HTTP: {str(e)[:100]}"

def _http_req(base_url: str, path: str, method: str = "GET", body: dict | None = None, timeout_s: float = 2,
              conn_holder: dict | None = None) -> tuple[int, str]:
    """GET or POST to loopback only. Return (status, body_text). Raise ValueError on non-loopback/redirect.
    conn_holder, if given, gets its "conn" key set to the live HTTPConnection right after connect, so a
    watchdog thread can close it out from under an in-flight request (defect 4: abort must close the
    generate conn before unload, or ollama won't unload mid-request)."""
    url = base_url + path
    # Enforce loopback: only 127.0.0.1, localhost, ::1; http scheme
    if url.startswith("http://127.0.0.1:") or url.startswith("http://localhost:"):
        host_port = url.replace("http://", "")
    elif url.startswith("http://[::1]:"):
        host_port = url.replace("http://", "").split("/", 1)[0]
    else:
        raise ValueError("WB_LOCAL_NON_LOOPBACK")

    try:
        host, rest = host_port.split(":", 1)
        port_and_path = rest.split("/", 1)
        port = int(port_and_path[0])
        path_part = "/" + port_and_path[1] if len(port_and_path) > 1 else "/"
    except Exception:
        raise ValueError("WB_LOCAL_HTTP")

    try:
        conn = http.client.HTTPConnection(host, port, timeout=timeout_s)
        if conn_holder is not None:
            conn_holder["conn"] = conn
        if method == "GET":
            conn.request("GET", path_part)
        else:
            body_text = json.dumps(body or {})
            conn.request("POST", path_part, body_text, {"Content-Type": "application/json"})
        resp = conn.getresponse()
        # Reject redirects
        if resp.status >= 300 and resp.status < 400:
            raise ValueError("WB_LOCAL_HTTP: redirect")
        result = resp.read().decode()
        conn.close()
        return resp.status, result
    except http.client.HTTPException as e:
        raise ValueError(f"WB_LOCAL_HTTP: {str(e)[:100]}")

def admit(model: str, snap: dict | None, model_size: int | None = None) -> tuple[bool, str]:
    """snap None -> reject WB_LOCAL_NO_TELEMETRY; free_pct < min_free_pct -> reject WB_LOCAL_LOW_MEMORY; free_bytes < size*model_headroom -> WB_LOCAL_MODEL_TOO_BIG."""
    if snap is None:
        return False, "WB_LOCAL_NO_TELEMETRY"
    min_free_pct = _CONFIG.get("min_free_pct", 35)
    if snap.get("free_pct", 0) < min_free_pct:
        return False, "WB_LOCAL_LOW_MEMORY"
    # Check model headroom: need free_bytes >= model_size * model_headroom
    if model_size is not None:
        headroom = _CONFIG.get("model_headroom", 1.25)
        needed = int(model_size * headroom)
        if snap.get("free_bytes", 0) < needed:
            return False, "WB_LOCAL_MODEL_TOO_BIG"
        # Projected admission: reject upfront any model whose footprint, once loaded,
        # would leave free_pct within projection_margin_pct of the watchdog's own abort
        # line -- catches models that pass the raw headroom check today but would trip
        # the watchdog abort moments after load (percent-scaled, no absolute GiB).
        total_bytes = snap.get("total_bytes", 0)
        if total_bytes > 0:
            abort_free_pct = _CONFIG.get("abort_free_pct", 25)
            projection_margin_pct = _CONFIG.get("projection_margin_pct", 5)
            projected_free_pct = snap.get("free_pct", 0) - (model_size * headroom / total_bytes * 100)
            if projected_free_pct < abort_free_pct + projection_margin_pct:
                return False, "WB_LOCAL_PROJECTED_LOW_MEMORY"
    return True, ""

def _estimate_tokens(prompt: str) -> int:
    """Estimate tokens = ceil(len(prompt.encode())/3)."""
    return math.ceil(len(prompt.encode()) / 3)

def _acquire_lock(lock_path: Path) -> bool:
    """Acquire exclusive lock LOCK_EX|LOCK_NB. Return file handle if locked, None if busy."""
    global _LOCK_HANDLE
    try:
        f = open(lock_path, "w")
        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        _LOCK_HANDLE = f
        return f
    except (BlockingIOError, OSError):
        return None

def _get_breaker_reason(state_dir: Path) -> str | None:
    """Return reason if breaker file present, else None."""
    breaker_path = state_dir / "ollama.disabled"
    if breaker_path.exists():
        try:
            data = json.loads(breaker_path.read_text())
            return data.get("reason")
        except Exception:
            return "WB_LOCAL_DISABLED"
    return None

def _write_breaker(state_dir: Path, reason: str) -> None:
    """Write breaker file with reason and timestamp."""
    state_dir.mkdir(parents=True, exist_ok=True)
    breaker_path = state_dir / "ollama.disabled"
    data = {"reason": reason, "ts": time.time()}
    breaker_path.write_text(json.dumps(data))

def _reset_breaker(state_dir: Path) -> None:
    """Clear breaker file."""
    breaker_path = state_dir / "ollama.disabled"
    if breaker_path.exists():
        breaker_path.unlink()

def _unload_and_verify(endpoint: str, model: str, state_dir: Path) -> bool:
    """POST unload, poll /api/ps until model absent <= unload_verify_s. Return True if verified, False if timeout."""
    unload_verify_s = _CONFIG.get("unload_verify_s", 5)
    try:
        unload_body = {"model": model, "keep_alive": 0}
        _http_req(endpoint, "/api/generate", method="POST", body=unload_body, timeout_s=10)
    except Exception:
        pass

    # Verify unload
    start_unload = time.time()
    while time.time() - start_unload < unload_verify_s:
        try:
            status, body = _http_req(endpoint, "/api/ps", method="GET", timeout_s=2)
            if status == 200:
                data = json.loads(body)
                loaded = [m.get("name") for m in data.get("models", [])]
                if model not in loaded:
                    return True  # Unload verified
        except Exception:
            pass
        time.sleep(0.5)

    # Unload not confirmed
    return False

def main():
    """Read prompt from stdin; model arg. Checks: breaker, lock, budget, telemetry+admit. POST /api/generate with watchdog."""
    global _LOCK_HANDLE

    # Handle --reset flag
    if len(sys.argv) > 1 and sys.argv[1] == "--reset":
        state_dir = _state_dir()
        _reset_breaker(state_dir)
        print("ollama breaker cleared", file=sys.stderr)
        sys.exit(0)

    if len(sys.argv) < 2:
        print("usage: ollama <model>", file=sys.stderr)
        sys.exit(2)

    model = sys.argv[1]
    allowlist = _load_allowlist()
    if model not in allowlist:
        print("WB_LOCAL_MODEL_NOT_ALLOWED", file=sys.stderr)
        sys.exit(2)

    state_dir = _state_dir()
    state_dir.mkdir(parents=True, exist_ok=True)

    # Check breaker
    breaker_reason = _get_breaker_reason(state_dir)
    if breaker_reason:
        print(f"WB_LOCAL_DISABLED: {breaker_reason}", file=sys.stderr)
        sys.exit(2)

    # Acquire lock
    lock_path = state_dir / "ollama.lock"
    lock_handle = _acquire_lock(lock_path)
    if lock_handle is None:
        print("WB_LOCAL_BUSY", file=sys.stderr)
        sys.exit(2)

    try:
        # Read prompt from stdin
        prompt = sys.stdin.read()

        # Check input budget
        max_input_tokens = _CONFIG.get("max_input_tokens", 3072)
        estimated_tokens = _estimate_tokens(prompt)
        if estimated_tokens > max_input_tokens:
            print("WB_LOCAL_INPUT_TOO_LARGE", file=sys.stderr)
            sys.exit(2)

        # Check telemetry
        snap = mem_snapshot()
        if snap is None:
            print("WB_LOCAL_NO_TELEMETRY", file=sys.stderr)
            sys.exit(2)

        # Get model size from /api/tags for admit check. Distinguish "couldn't reach tags"
        # (exit 1, no breaker -- server down) from "reachable but model not listed" (exit 2).
        endpoint = _CONFIG.get("endpoint", "http://127.0.0.1:11434")
        model_size = None
        tags_status = None
        try:
            tags_status, tags_body = _http_req(endpoint, "/api/tags", method="GET", timeout_s=_CONFIG.get("connect_timeout_s", 2))
        except Exception:
            tags_status = None

        if tags_status != 200:
            print("WB_LOCAL_HTTP: tags unavailable", file=sys.stderr)
            sys.exit(1)

        try:
            data = json.loads(tags_body)
            for m in data.get("models", []):
                if m.get("name") == model:
                    model_size = m.get("size")
                    break
        except Exception:
            model_size = None

        if model_size is None:
            print("WB_LOCAL_MODEL_NOT_ALLOWED", file=sys.stderr)
            sys.exit(2)

        # Check admit
        admitted, reason = admit(model, snap, model_size=model_size)
        if not admitted:
            print(reason, file=sys.stderr)
            sys.exit(2)

        # POST /api/generate in worker thread, watchdog in main
        deadline_s = _CONFIG.get("deadline_s", 90)
        num_ctx = _CONFIG.get("num_ctx", 4096)
        num_predict = _CONFIG.get("num_predict", 512)
        no_think_models = _CONFIG.get("no_think_models", [])
        watchdog_interval_s = _CONFIG.get("watchdog_interval_s", 2)
        abort_free_pct = _CONFIG.get("abort_free_pct", 25)
        max_swap_growth_pct = _CONFIG.get("max_swap_growth_pct", 2)
        worker_timeout_s = _CONFIG.get("worker_timeout_s", 100)

        req_body = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "keep_alive": 0,
            "options": {
                "num_ctx": num_ctx,
                "num_predict": num_predict
            }
        }
        if model in no_think_models:
            req_body["think"] = False

        # result also doubles as the conn_holder passed to _http_req, so the watchdog can
        # close result["conn"] from the main thread to abort an in-flight generate (defect 4).
        result = {"output": None, "error": None, "http_status": None, "connect_fail": False, "conn": None}

        def worker_fn():
            try:
                status, body = _http_req(endpoint, "/api/generate", method="POST", body=req_body,
                                         timeout_s=worker_timeout_s, conn_holder=result)
                if status != 200:
                    result["http_status"] = status
                    result["error"] = f"WB_LOCAL_HTTP: HTTP {status}"
                    result["connect_fail"] = False
                    return
                data = json.loads(body)
                result["output"] = data.get("response", "")
            except ValueError as e:
                # raised by _http_req for non-loopback/redirect/malformed target -- not a
                # connect-fail, server was reachable enough to answer wrong.
                result["error"] = str(e)
                result["connect_fail"] = False
            except OSError as e:
                # connect refused / timed out / socket-level failure = server down.
                # Spec: no breaker for this case.
                result["error"] = f"WB_LOCAL_HTTP: {str(e)[:100]}"
                result["connect_fail"] = True
            except Exception as e:
                result["error"] = f"WB_LOCAL_HTTP: {str(e)[:100]}"
                result["connect_fail"] = False

        worker = threading.Thread(target=worker_fn, daemon=True)
        worker.start()

        start_time = time.time()
        snap_baseline = snap.copy()
        watchdog_abort_reason = None

        while worker.is_alive():
            elapsed = time.time() - start_time

            # Check deadline
            if elapsed > deadline_s:
                watchdog_abort_reason = "WB_LOCAL_DEADLINE"
                break

            # Telemetry lost mid-run -> abort. Do NOT silently continue (defect 1).
            snap_current = mem_snapshot()
            if snap_current is None:
                watchdog_abort_reason = "WB_LOCAL_TELEMETRY_LOST"
                break

            # Check free memory
            if snap_current.get("free_pct", 0) < abort_free_pct:
                watchdog_abort_reason = "WB_LOCAL_LOW_MEMORY_ABORT"
                break

            # Check swap growth
            swap_growth_b = snap_current.get("swap_used_bytes", 0) - snap_baseline.get("swap_used_bytes", 0)
            max_growth_b = snap_baseline.get("total_bytes", 1) * max_swap_growth_pct / 100
            if swap_growth_b > max_growth_b:
                watchdog_abort_reason = "WB_LOCAL_SWAP_GROWTH"
                break

            time.sleep(watchdog_interval_s)

        # On abort, close the in-flight generate conn first -- ollama won't unload a model
        # mid-request, so the worker's open HTTPConnection must die before we try (defect 4).
        if watchdog_abort_reason and result.get("conn") is not None:
            try:
                result["conn"].close()
            except Exception:
                pass

        # Unload + verify (always run after any generate path)
        unload_ok = _unload_and_verify(endpoint, model, state_dir)

        # Handle abort (watchdog triggered)
        if watchdog_abort_reason:
            if not unload_ok:
                # If unload failed, note both reasons
                _write_breaker(state_dir, f"{watchdog_abort_reason}; unload failed")
            else:
                _write_breaker(state_dir, watchdog_abort_reason)
            print(watchdog_abort_reason, file=sys.stderr)
            sys.exit(3)

        # Handle unload failure (if no watchdog abort)
        if not unload_ok:
            _write_breaker(state_dir, "WB_LOCAL_UNLOAD_UNCONFIRMED")
            print("WB_LOCAL_UNLOAD_UNCONFIRMED", file=sys.stderr)
            sys.exit(4)

        # Worker done, check result. connect_fail (server down) -> no breaker; any other
        # HTTP failure (non-200, malformed body, redirect) -> breaker.
        if result["error"]:
            reason = result["error"]
            if not result["connect_fail"]:
                _write_breaker(state_dir, reason)
            print(reason, file=sys.stderr)
            sys.exit(1)

        # Success: print response, exit 0
        if result["output"] is not None:
            print(result["output"], end="")
        sys.exit(0)

    finally:
        # Close lock handle (do NOT unlink - keeps exclusivity for waiters)
        if _LOCK_HANDLE:
            try:
                _LOCK_HANDLE.close()
            except Exception:
                pass
            _LOCK_HANDLE = None

if __name__ == "__main__":
    main()
