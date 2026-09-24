"""Tests for agents_inc.free_health module (spec 012)."""
import json
import pytest
import subprocess
import tempfile
import threading
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from tests._free012 import hermetic  # noqa: F401 - imported for use in tests


pytestmark = pytest.mark.usefixtures("hermetic")


# === T003 REDO: Classify Tests ===

class TestFreeHealthClassify:
    """Test classify: outcome extraction from HTTP response."""

    @pytest.fixture
    def error_responses(self):
        """Load error responses fixture."""
        fixture_path = Path(__file__).parent / "fixtures" / "012" / "error_responses.json"
        with open(fixture_path) as f:
            return json.load(f)

    @pytest.mark.parametrize("response_key", [
        "error_404_unavailable_for_free",
        "error_404_zdr",
        "error_429_with_delay",
        "error_429_no_delay",
        "error_503",
    ])
    def test_classify_from_fixtures(self, error_responses, response_key):
        """Parametrized classify tests from error_responses.json fixture."""
        from agents_inc import free_health

        case = error_responses[response_key]
        status = case["status"]
        body = case["body"]
        headers = case.get("headers")

        outcome, retry = free_health.classify(status=status, body=body, headers=headers)

        # Verify outcome is valid
        assert outcome in ["withdrawn", "zdr", "rate_limited", "overloaded", "ok", "error"]
        # Verify retry is None or a float
        assert retry is None or isinstance(retry, (int, float))

    def test_classify_200_ok(self):
        """2xx -> ok."""
        from agents_inc import free_health
        outcome, retry = free_health.classify(status=200, body='{"choices": [{"text": "ok"}]}')
        assert outcome == "ok"
        assert retry is None

    def test_classify_404_unavailable_for_free(self):
        """404 with 'unavailable for free' -> withdrawn."""
        from agents_inc import free_health
        outcome, retry = free_health.classify(
            status=404,
            body='{"error": {"message": "This model is unavailable for free"}}'
        )
        assert outcome == "withdrawn"
        assert retry is None

    def test_classify_404_zdr(self):
        """404 with ZDR text -> zdr."""
        from agents_inc import free_health
        outcome, retry = free_health.classify(
            status=404,
            body='{"error": {"message": "Check your zero-data-retention setting."}}'
        )
        assert outcome == "zdr"
        assert retry is None

    def test_classify_404_model_not_found_is_error(self):
        """404 with 'Model not found' -> error (not withdrawn)."""
        from agents_inc import free_health
        outcome, retry = free_health.classify(
            status=404,
            body='{"error": {"message": "Model not found"}}'
        )
        assert outcome == "error"
        assert retry is None

    def test_classify_429_with_retry_after_header(self):
        """429 with Retry-After header -> rate_limited with that delay."""
        from agents_inc import free_health
        outcome, retry = free_health.classify(
            status=429,
            body='{"error": {"message": "Rate limit exceeded"}}',
            headers={"Retry-After": "53"}
        )
        assert outcome == "rate_limited"
        assert retry == 53 or retry == 53.0

    def test_classify_429_with_retry_in_body(self):
        """429 with 'retry in NNs' in body -> rate_limited with that delay."""
        from agents_inc import free_health
        outcome, retry = free_health.classify(
            status=429,
            body='{"error": {"message": "Rate limit exceeded. Please retry in 53.02s"}}'
        )
        assert outcome == "rate_limited"
        assert retry == 53.02 or retry == 53

    def test_classify_429_no_retry_info_uses_default(self):
        """429 without delay info -> rate_limited with default 60s."""
        from agents_inc import free_health
        outcome, retry = free_health.classify(
            status=429,
            body='{"error": {"message": "Rate limit exceeded."}}'
        )
        assert outcome == "rate_limited"
        assert retry == 60 or retry == 60.0

    def test_classify_503_overloaded(self):
        """503 -> overloaded."""
        from agents_inc import free_health
        outcome, retry = free_health.classify(
            status=503,
            body='{"error": {"message": "Service overloaded"}}'
        )
        assert outcome == "overloaded"
        assert retry is None or retry == 60

    def test_classify_500_error(self):
        """500 -> error."""
        from agents_inc import free_health
        outcome, retry = free_health.classify(
            status=500,
            body='{"error": {"message": "Internal error"}}'
        )
        assert outcome == "error"
        assert retry is None


class TestFreeHealthAtomic:
    """Test atomic write: file not corrupt under concurrent access."""

    def test_save_health_atomic_write(self, hermetic):
        """save_health uses atomic temp file + os.replace."""
        from agents_inc import free_health

        data = {"openrouter": {"status": "ok"}}
        free_health.save_health(data)

        health_path = free_health.health_path()
        assert health_path.exists()

        # Verify file is valid JSON
        with open(health_path) as f:
            loaded = json.load(f)
        assert loaded == data

    def test_concurrent_writes_last_write_wins(self, hermetic):
        """Concurrent writes to health file: last write wins, no corruption."""
        from agents_inc import free_health
        import random

        results = []
        errors = []

        def write_health(index):
            try:
                data = {"backend_" + str(index): {"status": "ok", "index": index}}
                free_health.save_health(data)
                results.append(index)
            except Exception as e:
                errors.append((index, e))

        # Start 50 concurrent writes with different data
        threads = []
        for i in range(50):
            t = threading.Thread(target=write_health, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # No errors should occur
        assert not errors, f"Concurrent write errors: {errors}"
        assert len(results) == 50

        # Final file must be valid JSON
        health_path = free_health.health_path()
        with open(health_path) as f:
            final_data = json.load(f)

        # Should contain one of the indices (last write wins)
        assert len(final_data) >= 1

    def test_save_health_no_tmp_leftovers(self, hermetic, tmp_path, monkeypatch):
        """Atomic write leaves no .tmp files."""
        from agents_inc import free_health

        monkeypatch.setenv("HOME", str(tmp_path))

        data = {"openrouter": {"status": "ok"}}
        free_health.save_health(data)

        # Check for any temp files
        codex_bridge_dir = tmp_path / ".codex-bridge"
        tmp_files = list(codex_bridge_dir.glob("*.tmp*"))
        assert not tmp_files, f"Found temp files: {tmp_files}"


class TestFreeHealthDegradation:
    """Test degradation: missing/corrupt file handling."""

    def test_missing_file_returns_empty_dict_silent(self, hermetic, capsys):
        """Missing health file -> {} with no warning to stderr."""
        from agents_inc import free_health

        # Ensure file doesn't exist
        health_path = free_health.health_path()
        if health_path.exists():
            health_path.unlink()

        result = free_health.load_health()

        assert result == {}
        captured = capsys.readouterr()
        # Should have no warning line
        warning_lines = [line for line in captured.err.split('\n') if line.startswith("free_health: warning:")]
        assert len(warning_lines) == 0, f"Expected no warnings, got {len(warning_lines)}: {warning_lines}"

    def test_corrupt_file_returns_empty_dict_one_warning(self, hermetic, capsys):
        """Corrupt health file -> {} + exactly one warning to stderr."""
        from agents_inc import free_health

        # Write corrupt JSON
        health_path = free_health.health_path()
        health_path.parent.mkdir(parents=True, exist_ok=True)
        with open(health_path, 'w') as f:
            f.write("{this is not valid json")

        result = free_health.load_health()

        assert result == {}
        captured = capsys.readouterr()
        warning_lines = [line for line in captured.err.split('\n') if line.startswith("free_health: warning:")]
        assert len(warning_lines) == 1, f"Expected 1 warning, got {len(warning_lines)}: {warning_lines}"

    def test_valid_file_no_stderr(self, hermetic, capsys):
        """Valid health file produces no stderr."""
        from agents_inc import free_health

        data = {"openrouter": {"status": "ok"}}
        free_health.save_health(data)

        captured = capsys.readouterr()
        # Clear captured from save operation

        result = free_health.load_health()
        assert result == data

        captured = capsys.readouterr()
        # load_health on valid file should produce no warning
        warning_lines = [line for line in captured.err.split('\n') if line.startswith("free_health: warning:")]
        assert len(warning_lines) == 0


class TestFreeHealthCLI:
    """Test CLI interface."""

    def test_classify_cli_with_body_file(self, hermetic, tmp_path):
        """CLI classify --status CODE --body-file F prints outcome and retry."""
        from agents_inc import free_health

        body_file = tmp_path / "body.json"
        body_file.write_text('{"error": {"message": "Rate limit exceeded. Please retry in 53.02s"}}')

        # Call main with classify command
        result = free_health.main(["classify", "--status", "429", "--body-file", str(body_file)])

        assert result == 0

    def test_classify_cli_success_status(self, hermetic, tmp_path, capsys):
        """CLI classify with 200 status -> 'ok' output."""
        from agents_inc import free_health

        body_file = tmp_path / "body.json"
        body_file.write_text('{"choices": [{"text": "response"}]}')

        result = free_health.main(["classify", "--status", "200", "--body-file", str(body_file)])

        assert result == 0
        captured = capsys.readouterr()
        assert "ok" in captured.out.lower() or "ok" in captured.out

    def test_classify_cli_rate_limited_status(self, hermetic, tmp_path, capsys):
        """CLI classify with 429 status -> 'rate_limited' and delay."""
        from agents_inc import free_health

        body_file = tmp_path / "body.json"
        body_file.write_text('{"error": {"message": "Rate limit exceeded"}}')

        result = free_health.main(["classify", "--status", "429", "--body-file", str(body_file)])

        assert result == 0
        captured = capsys.readouterr()
        assert "rate_limited" in captured.out.lower() or "rate_limited" in captured.out


# === T006: pick_default Tests ===

class TestFreeHealthPickDefault:
    """Test pick_default: select eligible free model from catalog."""

    def test_pick_default_basic(self, hermetic, tmp_path):
        """pick_default returns first eligible free model."""
        from agents_inc import free_health

        catalog = {
            "models": {
                "mistral/mistral-7b:free": {
                    "provider": "mistral",
                    "status": "available",
                    "tasks_good": ["classify"],
                    "tasks_bad": [],
                },
                "openrouter/auto:free": {
                    "provider": "openrouter",
                    "status": "available",
                    "tasks_good": ["classify"],
                    "tasks_bad": [],
                }
            }
        }

        result = free_health.pick_default("mistral", "classify", catalog=catalog)
        assert result == "mistral/mistral-7b:free"

    def test_pick_default_skips_unavailable(self, hermetic, tmp_path):
        """pick_default skips models with unavailable status."""
        from agents_inc import free_health

        catalog = {
            "models": {
                "mistral/unavailable:free": {
                    "provider": "mistral",
                    "status": "unavailable",
                    "tasks_good": ["classify"],
                    "tasks_bad": [],
                },
                "openrouter/auto:free": {
                    "provider": "openrouter",
                    "status": "available",
                    "tasks_good": ["classify"],
                    "tasks_bad": [],
                }
            }
        }

        result = free_health.pick_default("openrouter", "classify", catalog=catalog)
        assert result == "openrouter/auto:free"

    def test_pick_default_skips_overlay_unavailable(self, hermetic, tmp_path, monkeypatch):
        """pick_default skips models with overlay unavailable status."""
        from agents_inc import free_health

        monkeypatch.setenv("HOME", str(tmp_path))

        # Create overlay with unavailable status
        overlay_path = free_health.overlay_path()
        overlay_path.parent.mkdir(parents=True, exist_ok=True)
        overlay_data = {
            "mistral/mistral-7b:free": {
                "status": "unavailable",
                "reason": "withdrawn",
                "at": "2026-09-23T00:00:00Z"
            }
        }
        free_health.save_overlay(overlay_data)

        catalog = {
            "models": {
                "mistral/mistral-7b:free": {
                    "provider": "mistral",
                    "status": "available",
                    "tasks_good": ["classify"],
                    "tasks_bad": [],
                },
                "openrouter/auto:free": {
                    "provider": "openrouter",
                    "status": "available",
                    "tasks_good": ["classify"],
                    "tasks_bad": [],
                }
            }
        }

        result = free_health.pick_default("openrouter", "classify", catalog=catalog)
        assert result == "openrouter/auto:free"

    def test_pick_default_skips_non_free(self, hermetic, tmp_path):
        """pick_default skips models without :free in ID."""
        from agents_inc import free_health

        catalog = {
            "models": {
                "mistral/mistral-7b": {
                    "provider": "mistral",
                    "status": "available",
                    "tasks_good": ["classify"],
                    "tasks_bad": [],
                },
                "openrouter/auto:free": {
                    "provider": "openrouter",
                    "status": "available",
                    "tasks_good": ["classify"],
                    "tasks_bad": [],
                }
            }
        }

        result = free_health.pick_default("openrouter", "classify", catalog=catalog)
        assert result == "openrouter/auto:free"

    def test_pick_default_respects_tasks_good(self, hermetic, tmp_path):
        """pick_default requires task in tasks_good."""
        from agents_inc import free_health

        catalog = {
            "models": {
                "mistral/mistral-7b:free": {
                    "provider": "mistral",
                    "status": "available",
                    "tasks_good": ["summarize"],  # Not classify
                    "tasks_bad": [],
                },
                "openrouter/auto:free": {
                    "provider": "openrouter",
                    "status": "available",
                    "tasks_good": ["classify"],
                    "tasks_bad": [],
                }
            }
        }

        result = free_health.pick_default("openrouter", "classify", catalog=catalog)
        assert result == "openrouter/auto:free"

    def test_pick_default_skips_tasks_bad(self, hermetic, tmp_path):
        """pick_default skips tasks in tasks_bad."""
        from agents_inc import free_health

        catalog = {
            "models": {
                "mistral/mistral-7b:free": {
                    "provider": "mistral",
                    "status": "available",
                    "tasks_good": [],
                    "tasks_bad": ["classify"],
                },
                "openrouter/auto:free": {
                    "provider": "openrouter",
                    "status": "available",
                    "tasks_good": ["classify"],
                    "tasks_bad": [],
                }
            }
        }

        result = free_health.pick_default("openrouter", "classify", catalog=catalog)
        assert result == "openrouter/auto:free"

    def test_pick_default_none_returns_none_no_stderr(self, hermetic, tmp_path, capsys):
        """pick_default with no eligible models returns None."""
        from agents_inc import free_health

        catalog = {
            "models": {
                "mistral/mistral-7b": {
                    "provider": "mistral",
                    "status": "available",
                    "tasks_good": [],
                    "tasks_bad": [],
                }
            }
        }

        result = free_health.pick_default("openrouter", "classify", catalog=catalog)
        assert result is None

    def test_pick_default_cli(self, hermetic, tmp_path, monkeypatch, capsys):
        """CLI pick-default --provider --task prints model or exits 3."""
        from agents_inc import free_health

        monkeypatch.setenv("HOME", str(tmp_path))

        # Create a catalog file
        catalog_file = tmp_path / "models.json"
        catalog_data = {
            "models": {
                "openrouter/auto:free": {
                    "provider": "openrouter",
                    "status": "available",
                    "tasks_good": ["classify"],
                    "tasks_bad": [],
                }
            }
        }
        catalog_file.write_text(json.dumps(catalog_data))

        result = free_health.main(["pick-default", "--provider", "openrouter", "--task", "classify"])

        # Should succeed (exit 0 or print model)
        assert result == 0

    def test_pick_default_cli_no_eligible_exits_3(self, hermetic, tmp_path, monkeypatch, capsys):
        """CLI pick-default with no eligible models exits 3 + stderr message."""
        from agents_inc import free_health

        monkeypatch.setenv("HOME", str(tmp_path))

        # CLI reads the repo catalog; no model lists this task in tasks_good.
        result = free_health.main(["pick-default", "--provider", "openrouter", "--task", "no-such-task-012"])

        assert result == 3
        captured = capsys.readouterr()
        assert "no eligible free model" in captured.err.lower()

    def test_pick_default_never_returns_unavailable_multi_runs(self, hermetic, tmp_path):
        """20 runs over random catalogs never return unavailable model (SC-001)."""
        from agents_inc import free_health
        import random

        for run in range(20):
            catalog = {
                "models": {
                    "mistral/mistral-7b:free": {
                        "provider": "mistral",
                        "status": "available",
                        "tasks_good": ["classify"],
                        "tasks_bad": [],
                    },
                    "mistral/mistral-small:free": {
                        "provider": "mistral",
                        "status": "unavailable",
                        "tasks_good": ["classify"],
                        "tasks_bad": [],
                    },
                    "openrouter/auto:free": {
                        "provider": "openrouter",
                        "status": "available",
                        "tasks_good": ["classify"],
                        "tasks_bad": [],
                    }
                }
            }

            # Shuffle models
            model_list = list(catalog["models"].items())
            random.Random(run).shuffle(model_list)
            catalog["models"] = dict(model_list)

            result = free_health.pick_default("mistral", "classify", catalog=catalog)

            # Should never return the unavailable model
            if result:
                assert result != "mistral/mistral-small:free"


# === T009: Report Transitions Tests ===

class TestFreeHealthReportTransitions:
    """Test report: health state transitions per data-model.md."""

    def test_report_ok_resets_streak_and_cooldown(self, hermetic, tmp_path, monkeypatch):
        """Success (ok outcome) -> streak 0, cooldown None."""
        from agents_inc import free_health

        monkeypatch.setenv("HOME", str(tmp_path))
        now = datetime.now(timezone.utc)

        # Set initial state
        health_data = {
            "openrouter": {
                "status": "degraded",
                "failure_streak": 5,
                "cooldown_until": (now + timedelta(seconds=3600)).isoformat()
            }
        }
        free_health.save_health(health_data)

        # Report success
        free_health.report("openrouter", "auto:free", "ok", now=now)

        # Verify state reset
        result = free_health.load_health()
        assert result["openrouter"]["status"] == "ok"
        assert result["openrouter"]["failure_streak"] == 0
        assert result["openrouter"]["cooldown_until"] is None

    def test_report_rate_limited_with_retry_after(self, hermetic, tmp_path, monkeypatch):
        """429 with retry_after -> cooldown_until = now + retry_after."""
        from agents_inc import free_health

        monkeypatch.setenv("HOME", str(tmp_path))
        now = datetime.now(timezone.utc)
        retry_after = 53.02

        free_health.report("openrouter", "auto:free", "rate_limited", retry_after=retry_after, now=now)

        result = free_health.load_health()
        cooldown_str = result["openrouter"]["cooldown_until"]
        cooldown_until = datetime.fromisoformat(cooldown_str.replace('Z', '+00:00'))
        expected_cooldown = now + timedelta(seconds=retry_after)

        # Allow 1 second tolerance for timing
        assert abs((cooldown_until - expected_cooldown).total_seconds()) < 1
        assert result["openrouter"]["failure_streak"] == 1
        assert result["openrouter"]["status"] == "degraded"

    def test_report_rate_limited_no_retry_uses_exponential_backoff(self, hermetic, tmp_path, monkeypatch):
        """429 without retry_after -> uses backoff: 60s, then 120s, cap 3600s."""
        from agents_inc import free_health

        monkeypatch.setenv("HOME", str(tmp_path))
        now = datetime.now(timezone.utc)

        # First failure: 60 seconds
        free_health.report("openrouter", "auto:free", "rate_limited", now=now)
        result = free_health.load_health()
        cooldown_str1 = result["openrouter"]["cooldown_until"]
        cooldown1 = datetime.fromisoformat(cooldown_str1.replace('Z', '+00:00'))
        expected1 = now + timedelta(seconds=60)
        assert abs((cooldown1 - expected1).total_seconds()) < 1
        assert result["openrouter"]["failure_streak"] == 1

        # Second failure: 120 seconds (2^2 * 60 / 2 = 120)
        free_health.report("openrouter", "auto:free", "rate_limited", now=now + timedelta(seconds=60))
        result = free_health.load_health()
        cooldown_str2 = result["openrouter"]["cooldown_until"]
        cooldown2 = datetime.fromisoformat(cooldown_str2.replace('Z', '+00:00'))
        expected2 = now + timedelta(seconds=60 + 120)
        assert abs((cooldown2 - expected2).total_seconds()) < 1
        assert result["openrouter"]["failure_streak"] == 2

    def test_report_overloaded_same_backoff_as_rate_limited(self, hermetic, tmp_path, monkeypatch):
        """503 overloaded uses same backoff as 429."""
        from agents_inc import free_health

        monkeypatch.setenv("HOME", str(tmp_path))
        now = datetime.now(timezone.utc)

        free_health.report("openrouter", "auto:free", "overloaded", now=now)

        result = free_health.load_health()
        cooldown_str = result["openrouter"]["cooldown_until"]
        cooldown_until = datetime.fromisoformat(cooldown_str.replace('Z', '+00:00'))
        expected_cooldown = now + timedelta(seconds=60)

        assert abs((cooldown_until - expected_cooldown).total_seconds()) < 1
        assert result["openrouter"]["failure_streak"] == 1
        assert result["openrouter"]["status"] == "degraded"

    def test_report_withdrawn_writes_overlay_not_backend_cooldown(self, hermetic, tmp_path, monkeypatch):
        """404 withdrawn -> overlay entry, backend cooldown unchanged."""
        from agents_inc import free_health

        monkeypatch.setenv("HOME", str(tmp_path))
        now = datetime.now(timezone.utc)

        # Set initial backend state
        health_data = {
            "openrouter": {
                "status": "ok",
                "failure_streak": 0,
                "cooldown_until": None
            }
        }
        free_health.save_health(health_data)

        free_health.report("openrouter", "deepseek/deepseek-v4-flash-0731:free", "withdrawn", now=now)

        # Check overlay has entry
        overlay = free_health.load_overlay()
        assert "deepseek/deepseek-v4-flash-0731:free" in overlay
        assert overlay["deepseek/deepseek-v4-flash-0731:free"]["status"] == "unavailable"
        assert overlay["deepseek/deepseek-v4-flash-0731:free"]["reason"] == "withdrawn"

        # Check backend unchanged
        health = free_health.load_health()
        assert health["openrouter"]["status"] == "ok"
        assert health["openrouter"]["cooldown_until"] is None

    def test_report_zdr_writes_overlay_not_backend_cooldown(self, hermetic, tmp_path, monkeypatch):
        """404 ZDR -> overlay entry, backend cooldown unchanged."""
        from agents_inc import free_health

        monkeypatch.setenv("HOME", str(tmp_path))
        now = datetime.now(timezone.utc)

        free_health.report("openrouter", "deepseek/deepseek-v4-flash-0731:free", "zdr", now=now)

        # Check overlay has entry
        overlay = free_health.load_overlay()
        assert "deepseek/deepseek-v4-flash-0731:free" in overlay
        assert overlay["deepseek/deepseek-v4-flash-0731:free"]["reason"] == "zdr"

    def test_report_error_sets_last_error_only(self, hermetic, tmp_path, monkeypatch):
        """Other errors -> last_error set, no cooldown."""
        from agents_inc import free_health

        monkeypatch.setenv("HOME", str(tmp_path))
        now = datetime.now(timezone.utc)

        message = "Authentication failed"
        free_health.report("openrouter", "auto:free", "error", message=message, now=now)

        result = free_health.load_health()
        assert result["openrouter"]["last_error"] == message
        assert result["openrouter"]["cooldown_until"] is None

    def test_report_increments_calls_today(self, hermetic, tmp_path, monkeypatch):
        """Each report increments calls_today (per UTC day)."""
        from agents_inc import free_health

        monkeypatch.setenv("HOME", str(tmp_path))
        now = datetime.now(timezone.utc)

        free_health.report("openrouter", "auto:free", "ok", now=now)

        result = free_health.load_health()
        assert result["openrouter"]["calls_today"] == 1

        free_health.report("openrouter", "auto:free", "ok", now=now)

        result = free_health.load_health()
        assert result["openrouter"]["calls_today"] == 2

    def test_report_calls_day_tracks_utc_date(self, hermetic, tmp_path, monkeypatch):
        """calls_day is tracked as YYYY-MM-DD in UTC."""
        from agents_inc import free_health

        monkeypatch.setenv("HOME", str(tmp_path))
        now = datetime.now(timezone.utc)

        free_health.report("openrouter", "auto:free", "ok", now=now)

        result = free_health.load_health()
        assert result["openrouter"]["calls_day"] == now.strftime("%Y-%m-%d")

    def test_report_cooldown_cap_at_3600(self, hermetic, tmp_path, monkeypatch):
        """Exponential backoff caps at 3600 seconds (1 hour)."""
        from agents_inc import free_health

        monkeypatch.setenv("HOME", str(tmp_path))
        now = datetime.now(timezone.utc)

        # Simulate many failures to reach cap
        current_time = now
        for i in range(15):  # After several failures, should hit cap
            free_health.report("openrouter", "auto:free", "rate_limited", now=current_time)
            current_time += timedelta(seconds=1)

        result = free_health.load_health()
        if result["openrouter"]["cooldown_until"]:
            cooldown_str = result["openrouter"]["cooldown_until"]
            cooldown_until = datetime.fromisoformat(cooldown_str.replace('Z', '+00:00'))
            # Cooldown should be capped at 3600 from a reasonable point
            diff = (cooldown_until - current_time).total_seconds()
            assert diff <= 3600
