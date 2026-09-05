#!/usr/bin/env python3
"""
Codex HTTP bridge. Executes prompts via local codex CLI.
Token required: CODEX_BRIDGE_TOKEN env var.
"""

import argparse
import glob
import hmac
import http.server
import json
import os
import subprocess
import sys
import tempfile
import threading
from datetime import datetime, timezone


def is_rate_limited(stderr):
    """
    Check if stderr indicates a rate limit / quota exhaustion.
    Returns True if any rate-limit keyword is found (case-insensitive).
    """
    if not stderr:
        return False
    stderr_lower = stderr.lower()
    rate_limit_keywords = ["rate limit", "rate_limit", "quota", "429", "too many requests", "usage limit"]
    return any(keyword in stderr_lower for keyword in rate_limit_keywords)


def resolve_actual_model(explicit_model, thread_id):
    """
    Resolve the concrete GPT model codex actually used for this turn.
    `codex exec --json` never emits the model on stdout (verified: thread.started/
    turn.started/item.completed/turn.completed carry no model field), but the CLI's
    own session rollout log at ~/.codex/sessions/**/*<thread_id>*.jsonl records it in
    the world_state event's payload.collaboration_mode.model field. Best-effort only;
    returns explicit_model when the caller pinned one, else looks up the resolved
    default, else None (never fails the request).
    """
    if explicit_model:
        return explicit_model
    if not thread_id:
        return None
    try:
        pattern = os.path.expanduser(f"~/.codex/sessions/**/*{thread_id}*.jsonl")
        matches = glob.glob(pattern, recursive=True)
        if not matches:
            return None
        with open(matches[0], "r") as f:
            for line in f:
                if '"collaboration_mode"' not in line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                model = obj.get("payload", {}).get("state", {}).get("collaboration_mode", {}).get("model")
                if model:
                    return model
    except OSError:
        pass
    return None


def append_usage_ledger(model, input_tokens, output_tokens):
    """
    Append usage record to ~/.codex-bridge/usage.jsonl.
    Strictly read-only on ~/.claude/. Creates ~/.codex-bridge/ if needed.
    Failure does NOT affect request success.
    """
    try:
        # Ensure ~/.codex-bridge/ exists (700)
        ledger_dir = os.path.expanduser("~/.codex-bridge")
        os.makedirs(ledger_dir, mode=0o700, exist_ok=True)

        # Prepare record
        ts = datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')
        record = {
            "ts": ts,
            "backend": "codex",
            "model": model,
            "input_tokens": input_tokens or 0,
            "output_tokens": output_tokens or 0
        }

        # Append to ledger (600 perms)
        ledger_path = os.path.join(ledger_dir, "usage.jsonl")
        with open(ledger_path, "a") as f:
            f.write(json.dumps(record) + "\n")

        # Ensure file perms are 600
        os.chmod(ledger_path, 0o600)
    except Exception as e:
        # Log to stderr but do NOT fail the request
        print(f"Warning: failed to append usage ledger: {e}", file=sys.stderr)


class CodexBridgeHandler(http.server.BaseHTTPRequestHandler):
    """HTTP request handler for codex bridge."""

    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok"}).encode())
        elif self.path == "/session":
            self.handle_session()
        else:
            self.send_error_json(404, "not found")

    def do_POST(self):
        if self.path == "/prompt":
            self.handle_prompt()
        elif self.path == "/reset":
            self.handle_reset()
        else:
            self.send_error_json(404, "not found")

    def handle_prompt(self):
        """Handle POST /prompt."""
        # Check auth header
        auth_token = self.headers.get("X-Auth-Token", "")
        expected_token = os.environ.get("CODEX_BRIDGE_TOKEN", "")
        if not hmac.compare_digest(auth_token, expected_token):
            self.send_error_json(401, "unauthorized")
            return

        # Check Content-Length
        content_length = self.headers.get("Content-Length")
        if content_length:
            try:
                length = int(content_length)
                if length > 1024 * 1024:  # 1 MiB
                    self.send_error_json(413, "payload too large")
                    return
            except ValueError:
                self.send_error_json(400, "invalid Content-Length")
                return

        # Read body
        try:
            body_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(body_length).decode("utf-8")
        except Exception as e:
            self.send_error_json(400, f"failed to read body: {e}")
            return

        # Parse JSON
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self.send_error_json(400, "invalid JSON")
            return

        # Validate required fields
        if "prompt" not in data:
            self.send_error_json(400, "missing required field: prompt")
            return

        prompt = data["prompt"]
        if not isinstance(prompt, str):
            self.send_error_json(400, "prompt must be a string")
            return

        # Check reset field
        reset = data.get("reset", False)
        if not isinstance(reset, bool):
            self.send_error_json(400, "reset must be a boolean")
            return

        # Determine model
        model = data.get("model") or self.server.default_model

        # Execute codex
        try:
            with self.server.codex_lock:
                # Handle reset
                if reset:
                    self.server.thread_id = None

                # Create temp file for output
                with tempfile.NamedTemporaryFile(mode="w+", suffix=".txt", delete=False) as tmp:
                    tmpfile = tmp.name

                try:
                    # Build command with correct subcommand ordering
                    cmd = ["codex", "exec"]
                    cmd.extend(["-s", self.server.sandbox])
                    if model:
                        cmd.extend(["-m", model])
                    if self.server.thread_id and not reset:
                        cmd.extend(["resume", self.server.thread_id])
                    cmd.extend(["--json", "--skip-git-repo-check", "-o", tmpfile, "-"])

                    result = subprocess.run(
                        cmd,
                        input=prompt,
                        capture_output=True,
                        text=True,
                        timeout=self.server.codex_timeout,
                        cwd=self.server.workdir,
                    )

                    # Parse JSONL events from stdout
                    usage = None
                    for line in result.stdout.split("\n"):
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            obj = json.loads(line)
                            if obj.get("type") == "thread.started":
                                self.server.thread_id = obj.get("thread_id")
                            elif obj.get("type") == "turn.completed":
                                usage = obj.get("usage")
                        except json.JSONDecodeError:
                            pass

                    # Read response from file
                    if result.returncode == 0:
                        try:
                            with open(tmpfile, "r") as f:
                                response_text = f.read().strip()
                        except Exception:
                            response_text = ""

                        if not response_text:
                            response_text = ""

                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self.end_headers()
                        response = {
                            "response": response_text,
                            "thread_id": self.server.thread_id,
                            "usage": usage,
                            "session_restarted": False,
                        }
                        self.wfile.write(json.dumps(response).encode())

                        # Append to usage ledger
                        if usage:
                            input_tokens = usage.get("input_tokens")
                            output_tokens = usage.get("output_tokens")
                            actual_model = resolve_actual_model(model, self.server.thread_id)
                            append_usage_ledger(actual_model, input_tokens, output_tokens)
                    elif self.server.thread_id and "resume" in cmd:
                        # Check for rate limit BEFORE attempting retry
                        stderr = result.stderr[-4000:] if result.stderr else ""
                        if is_rate_limited(stderr):
                            # Rate limited: return 429 immediately, do NOT retry
                            self.send_response(429)
                            self.send_header("Content-Type", "application/json")
                            self.end_headers()
                            response = {
                                "error": "rate limited",
                                "backend": "codex",
                                "detail": stderr[-500:] if stderr else ""
                            }
                            self.wfile.write(json.dumps(response).encode())
                        else:
                            # Not rate limited: retry as fresh
                            previous_thread_id = self.server.thread_id
                            first_attempt_stderr = stderr
                            self.server.thread_id = None
                            with tempfile.NamedTemporaryFile(mode="w+", suffix=".txt", delete=False) as tmp2:
                                tmpfile2 = tmp2.name

                            try:
                                # Retry as fresh (no resume)
                                cmd_retry = ["codex", "exec"]
                                cmd_retry.extend(["-s", self.server.sandbox])
                                if model:
                                    cmd_retry.extend(["-m", model])
                                cmd_retry.extend(["--json", "--skip-git-repo-check", "-o", tmpfile2, "-"])

                                result = subprocess.run(
                                    cmd_retry,
                                    input=prompt,
                                    capture_output=True,
                                    text=True,
                                    timeout=self.server.codex_timeout,
                                    cwd=self.server.workdir,
                                )

                                # Parse JSONL events from retry
                                usage = None
                                for line in result.stdout.split("\n"):
                                    line = line.strip()
                                    if not line:
                                        continue
                                    try:
                                        obj = json.loads(line)
                                        if obj.get("type") == "thread.started":
                                            self.server.thread_id = obj.get("thread_id")
                                        elif obj.get("type") == "turn.completed":
                                            usage = obj.get("usage")
                                    except json.JSONDecodeError:
                                        pass

                                if result.returncode == 0:
                                    try:
                                        with open(tmpfile2, "r") as f:
                                            response_text = f.read().strip()
                                    except Exception:
                                        response_text = ""

                                    self.send_response(200)
                                    self.send_header("Content-Type", "application/json")
                                    self.end_headers()
                                    # Escape restart_reason for safe JSON serialization
                                    restart_reason = first_attempt_stderr[:200] if first_attempt_stderr else "resume failed"
                                    restart_reason = restart_reason.replace("\n", "\\n").replace("\r", "\\r")
                                    response = {
                                        "response": response_text,
                                        "thread_id": self.server.thread_id,
                                        "usage": usage,
                                        "session_restarted": True,
                                        "previous_thread_id": previous_thread_id,
                                        "restart_reason": restart_reason,
                                    }
                                    self.wfile.write(json.dumps(response).encode())

                                    # Append to usage ledger
                                    if usage:
                                        input_tokens = usage.get("input_tokens")
                                        output_tokens = usage.get("output_tokens")
                                        actual_model = resolve_actual_model(model, self.server.thread_id)
                                        append_usage_ledger(actual_model, input_tokens, output_tokens)
                                else:
                                    stderr_retry = result.stderr[-4000:] if result.stderr else ""
                                    self.send_error_json(502, f"codex exited {result.returncode}", stderr_retry)
                            finally:
                                try:
                                    os.unlink(tmpfile2)
                                except Exception:
                                    pass
                    else:
                        stderr = result.stderr[-4000:] if result.stderr else ""
                        # Check for rate limit on non-resume failures too
                        if is_rate_limited(stderr):
                            self.send_response(429)
                            self.send_header("Content-Type", "application/json")
                            self.end_headers()
                            response = {
                                "error": "rate limited",
                                "backend": "codex",
                                "detail": stderr[-500:] if stderr else ""
                            }
                            self.wfile.write(json.dumps(response).encode())
                        else:
                            self.send_error_json(502, f"codex exited {result.returncode}", stderr)

                finally:
                    try:
                        os.unlink(tmpfile)
                    except Exception:
                        pass

        except FileNotFoundError:
            self.send_error_json(500, "codex CLI not found on PATH")
        except subprocess.TimeoutExpired:
            self.send_error_json(504, f"codex timed out after {self.server.codex_timeout}s")
        except Exception as e:
            self.send_error_json(500, str(e))

    def handle_session(self):
        """Handle GET /session."""
        # Check auth header
        auth_token = self.headers.get("X-Auth-Token", "")
        expected_token = os.environ.get("CODEX_BRIDGE_TOKEN", "")
        if not hmac.compare_digest(auth_token, expected_token):
            self.send_error_json(401, "unauthorized")
            return

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        response = {
            "thread_id": self.server.thread_id,
            "sandbox": self.server.sandbox
        }
        self.wfile.write(json.dumps(response).encode())

    def handle_reset(self):
        """Handle POST /reset."""
        # Check auth header
        auth_token = self.headers.get("X-Auth-Token", "")
        expected_token = os.environ.get("CODEX_BRIDGE_TOKEN", "")
        if not hmac.compare_digest(auth_token, expected_token):
            self.send_error_json(401, "unauthorized")
            return

        with self.server.codex_lock:
            self.server.thread_id = None

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        response = {"reset": True}
        self.wfile.write(json.dumps(response).encode())

    def send_error_json(self, code, message, stderr=""):
        """Send JSON error response."""
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        response = {"error": message}
        if stderr:
            response["stderr"] = stderr
        self.wfile.write(json.dumps(response).encode())

    def log_message(self, format, *args):
        """Override to log one-liner only."""
        status = args[1] if len(args) > 1 else "?"
        self.server.logger(f"{self.command} {self.path} {status}")


class CodexBridgeServer(http.server.ThreadingHTTPServer):
    """ThreadingHTTPServer with custom logging."""

    def __init__(self, *args, logger=None, timeout=60, default_model=None, workdir=None, sandbox=None, **kwargs):
        self.logger = logger or (lambda x: None)
        self.codex_timeout = timeout
        self.default_model = default_model
        self.workdir = workdir or os.getcwd()
        self.sandbox = sandbox or "workspace-write"
        self.thread_id = None
        self.codex_lock = threading.Lock()
        super().__init__(*args, **kwargs)


def main():
    parser = argparse.ArgumentParser(description="Codex HTTP bridge")
    parser.add_argument("--port", type=int, default=8787, help="Listen port")
    parser.add_argument("--host", default="127.0.0.1", help="Listen host")
    parser.add_argument("--timeout", type=int, default=60, help="Codex execution timeout (seconds)")
    parser.add_argument("--model", help="Default model for codex exec")
    parser.add_argument("--workdir", help="Working directory for codex exec (default: cwd)")
    parser.add_argument("--sandbox", choices=["read-only", "workspace-write", "danger-full-access"], default="workspace-write", help="Codex sandbox mode")
    args = parser.parse_args()

    # Validate danger-full-access requires explicit env var
    if args.sandbox == "danger-full-access":
        if not os.environ.get("CODEX_BRIDGE_ALLOW_DANGER"):
            print("Error: refusing --sandbox danger-full-access without CODEX_BRIDGE_ALLOW_DANGER=1", file=sys.stderr)
            sys.exit(1)

    # Check token
    token = os.environ.get("CODEX_BRIDGE_TOKEN")
    if not token:
        print("Error: CODEX_BRIDGE_TOKEN not set", file=sys.stderr)
        sys.exit(1)

    # Start server
    server_address = (args.host, args.port)
    server = CodexBridgeServer(
        server_address,
        CodexBridgeHandler,
        timeout=args.timeout,
        default_model=args.model,
        workdir=args.workdir,
        sandbox=args.sandbox,
        logger=print,
    )

    # Log startup
    model_str = f" (model: {args.model})" if args.model else ""
    workdir_str = f" (workdir: {args.workdir})" if args.workdir else ""
    sandbox_str = f" (sandbox: {args.sandbox})" if args.sandbox else ""
    print(f"Listening on {args.host}:{args.port} (timeout: {args.timeout}s{model_str}{workdir_str}{sandbox_str})")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutdown.")


if __name__ == "__main__":
    main()
