"""Tests for agents_inc.free_caps module (spec 012 T016)."""
import json
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
import pytest
from tests._free012 import hermetic  # noqa: F401 - imported for use in tests


pytestmark = pytest.mark.usefixtures("hermetic")


class TestCallsToday:
    """Test calls_today counting: from usage DB or health record."""

    def test_calls_today_from_usage_db(self, hermetic, tmp_path):
        """calls_today reads from usage DB for current UTC day."""
        from agents_inc import free_caps

        # Setup: create usage DB with rows for today and yesterday
        db_path = tmp_path / ".codex-bridge" / "usage.db"
        db_path.parent.mkdir(parents=True)

        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS usage(
                uid TEXT PRIMARY KEY,
                ts TEXT NOT NULL,
                day TEXT NOT NULL,
                backend TEXT NOT NULL,
                model TEXT,
                input_tokens INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                cache_read INTEGER DEFAULT 0,
                cache_write INTEGER DEFAULT 0,
                reasoning INTEGER DEFAULT 0
            )
        """)

        today = datetime.now(timezone.utc).date().isoformat()
        yesterday = (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()

        # Add 5 entries for today
        for i in range(5):
            conn.execute(
                "INSERT INTO usage (uid, ts, day, backend, model) VALUES (?, ?, ?, ?, ?)",
                (f"uid-today-{i}", datetime.now(timezone.utc).isoformat(), today, "openrouter", "model-x"),
            )

        # Add 3 entries for yesterday
        for i in range(3):
            conn.execute(
                "INSERT INTO usage (uid, ts, day, backend, model) VALUES (?, ?, ?, ?, ?)",
                (f"uid-yesterday-{i}", datetime.now(timezone.utc).isoformat(), yesterday, "openrouter", "model-x"),
            )

        conn.commit()
        conn.close()

        # calls_today should count only today's entries
        count = free_caps.calls_today("openrouter", db_path=str(db_path))
        assert count == 5, f"Expected 5 calls today, got {count}"

    def test_calls_today_missing_db_uses_health(self, hermetic, tmp_path):
        """calls_today falls back to health record when DB missing."""
        from agents_inc import free_caps, free_health

        # Setup: create health file with calls_today for today
        codex_dir = tmp_path / ".codex-bridge"
        codex_dir.mkdir()

        today = datetime.now(timezone.utc).date().isoformat()
        health_data = {
            "openrouter": {
                "status": "ok",
                "calls_day": today,
                "calls_today": 7,
            }
        }
        (codex_dir / "backend-health.json").write_text(json.dumps(health_data))

        # calls_today should use health record
        count = free_caps.calls_today("openrouter", db_path=str(codex_dir / "usage.db"))
        assert count == 7, f"Expected 7 calls from health, got {count}"

    def test_calls_today_uses_max_of_db_and_health(self, hermetic, tmp_path):
        """calls_today returns max of DB and health record."""
        from agents_inc import free_caps

        # Setup: create both DB and health
        db_path = tmp_path / ".codex-bridge" / "usage.db"
        db_path.parent.mkdir(parents=True)

        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS usage(
                uid TEXT PRIMARY KEY,
                ts TEXT NOT NULL,
                day TEXT NOT NULL,
                backend TEXT NOT NULL,
                model TEXT,
                input_tokens INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                cache_read INTEGER DEFAULT 0,
                cache_write INTEGER DEFAULT 0,
                reasoning INTEGER DEFAULT 0
            )
        """)

        today = datetime.now(timezone.utc).date().isoformat()
        for i in range(3):
            conn.execute(
                "INSERT INTO usage (uid, ts, day, backend, model) VALUES (?, ?, ?, ?, ?)",
                (f"uid-{i}", datetime.now(timezone.utc).isoformat(), today, "openrouter", "model-x"),
            )
        conn.commit()
        conn.close()

        # Health has more
        today_iso = datetime.now(timezone.utc).date().isoformat()
        health_data = {
            "openrouter": {
                "status": "ok",
                "calls_day": today_iso,
                "calls_today": 8,
            }
        }
        (db_path.parent / "backend-health.json").write_text(json.dumps(health_data))

        count = free_caps.calls_today("openrouter", db_path=str(db_path))
        assert count == 8, f"Expected max(3 from DB, 8 from health) = 8, got {count}"

    def test_calls_today_resets_on_day_boundary(self, hermetic, tmp_path, monkeypatch):
        """calls_today resets when calendar day changes in UTC."""
        from agents_inc import free_caps

        # Setup: create health with yesterday's data
        codex_dir = tmp_path / ".codex-bridge"
        codex_dir.mkdir()

        yesterday = (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()
        health_data = {
            "openrouter": {
                "status": "ok",
                "calls_day": yesterday,
                "calls_today": 42,  # From yesterday
            }
        }
        (codex_dir / "backend-health.json").write_text(json.dumps(health_data))

        # calls_today should return 0 (different day)
        count = free_caps.calls_today("openrouter", db_path=str(codex_dir / "usage.db"))
        assert count == 0, f"Expected 0 for different day, got {count}"


class TestCapFor:
    """Test cap_for: read from free-caps.json or routing.json."""

    def test_cap_for_probed_wins_over_configured(self, hermetic, tmp_path):
        """cap_for returns probed cap from free-caps.json over routing.json."""
        from agents_inc import free_caps

        codex_dir = tmp_path / ".codex-bridge"
        codex_dir.mkdir()

        # Create free-caps.json with probed value
        caps_data = {
            "openrouter": {
                "cap": 100,
                "source": "probe",
                "at": datetime.now(timezone.utc).isoformat(),
            }
        }
        (codex_dir / "free-caps.json").write_text(json.dumps(caps_data))

        # cap_for should return 100 (probed), not 50 (configured)
        cap = free_caps.cap_for("openrouter")
        assert cap == 100, f"Expected probed cap 100, got {cap}"

    def test_cap_for_configured_default(self, hermetic, tmp_path):
        """cap_for returns configured cap from routing.json when not probed."""
        from agents_inc import free_caps

        # No free-caps.json, so uses routing.json
        cap = free_caps.cap_for("mistral")
        # From routing.json daily_caps
        assert cap == 500, f"Expected configured cap 500 for mistral, got {cap}"

    def test_cap_for_none_if_unconfigured(self, hermetic, tmp_path):
        """cap_for returns None if provider not configured."""
        from agents_inc import free_caps

        cap = free_caps.cap_for("unknown-provider")
        assert cap is None, f"Expected None for unconfigured provider, got {cap}"


class TestAtCap:
    """Test at_cap: check if provider has reached daily limit."""

    def test_at_cap_true_at_limit(self, hermetic, tmp_path):
        """at_cap returns True when calls_today >= cap."""
        from agents_inc import free_caps

        codex_dir = tmp_path / ".codex-bridge"
        codex_dir.mkdir()

        # Set up usage: 50 calls today
        db_path = codex_dir / "usage.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS usage(
                uid TEXT PRIMARY KEY,
                ts TEXT NOT NULL,
                day TEXT NOT NULL,
                backend TEXT NOT NULL,
                model TEXT,
                input_tokens INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                cache_read INTEGER DEFAULT 0,
                cache_write INTEGER DEFAULT 0,
                reasoning INTEGER DEFAULT 0
            )
        """)

        today = datetime.now(timezone.utc).date().isoformat()
        for i in range(50):
            conn.execute(
                "INSERT INTO usage (uid, ts, day, backend, model) VALUES (?, ?, ?, ?, ?)",
                (f"uid-{i}", datetime.now(timezone.utc).isoformat(), today, "openrouter", "model-x"),
            )
        conn.commit()
        conn.close()

        # openrouter default cap is 50
        result = free_caps.at_cap("openrouter", db_path=str(db_path))
        assert result is True, "Expected at_cap=True when at limit"

    def test_at_cap_false_below_limit(self, hermetic, tmp_path):
        """at_cap returns False when calls_today < cap."""
        from agents_inc import free_caps

        codex_dir = tmp_path / ".codex-bridge"
        codex_dir.mkdir()

        # Set up usage: 10 calls today (below 50 cap)
        db_path = codex_dir / "usage.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS usage(
                uid TEXT PRIMARY KEY,
                ts TEXT NOT NULL,
                day TEXT NOT NULL,
                backend TEXT NOT NULL,
                model TEXT,
                input_tokens INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                cache_read INTEGER DEFAULT 0,
                cache_write INTEGER DEFAULT 0,
                reasoning INTEGER DEFAULT 0
            )
        """)

        today = datetime.now(timezone.utc).date().isoformat()
        for i in range(10):
            conn.execute(
                "INSERT INTO usage (uid, ts, day, backend, model) VALUES (?, ?, ?, ?, ?)",
                (f"uid-{i}", datetime.now(timezone.utc).isoformat(), today, "openrouter", "model-x"),
            )
        conn.commit()
        conn.close()

        result = free_caps.at_cap("openrouter", db_path=str(db_path))
        assert result is False, "Expected at_cap=False when below limit"

    def test_at_cap_false_no_cap(self, hermetic, tmp_path):
        """at_cap returns False when cap is None."""
        from agents_inc import free_caps

        # Unconfigured provider has no cap
        result = free_caps.at_cap("unknown-provider")
        assert result is False, "Expected at_cap=False when cap is None"


class TestProbeOpenRouter:
    """Test probe_openrouter: fetch and store key limits."""

    def test_probe_openrouter_from_fixture(self, hermetic, tmp_path):
        """probe_openrouter with from_file reads fixture and writes free-caps.json."""
        from agents_inc import free_caps

        codex_dir = tmp_path / ".codex-bridge"
        codex_dir.mkdir()

        fixture_path = Path(__file__).parent / "fixtures" / "012" / "openrouter_key_limits.json"
        result = free_caps.probe_openrouter(from_file=str(fixture_path))

        # Check result
        assert result is not None
        assert "openrouter" in result

        # Check file written
        caps_path = codex_dir / "free-caps.json"
        assert caps_path.exists(), "free-caps.json should be written"

        with open(caps_path) as f:
            caps_data = json.load(f)

        assert "openrouter" in caps_data
        assert caps_data["openrouter"]["cap"] == 50  # daily_requests_limit from fixture

    def test_probe_openrouter_never_prints_key(self, hermetic, tmp_path, capsys):
        """probe_openrouter never prints API key to stdout/stderr."""
        from agents_inc import free_caps
        import os

        codex_dir = tmp_path / ".codex-bridge"
        codex_dir.mkdir()

        # Set fake API key
        os.environ["OPEN_ROUTER_API_KEY"] = "sk-or-FAKE-SENTINEL-1234567890"

        fixture_path = Path(__file__).parent / "fixtures" / "012" / "openrouter_key_limits.json"
        free_caps.probe_openrouter(from_file=str(fixture_path))

        captured = capsys.readouterr()
        assert "FAKE-SENTINEL-1234567890" not in captured.out, "Key found in stdout"
        assert "FAKE-SENTINEL-1234567890" not in captured.err, "Key found in stderr"
        assert "sk-or-" not in captured.out, "API key pattern found in stdout"
        assert "sk-or-" not in captured.err, "API key pattern found in stderr"

    def test_probe_openrouter_cli(self, hermetic, tmp_path, capsys):
        """CLI python3 -m agents_inc.free_caps probe-openrouter with fixture."""
        from agents_inc import free_caps
        import os

        codex_dir = tmp_path / ".codex-bridge"
        codex_dir.mkdir()

        fixture_path = Path(__file__).parent / "fixtures" / "012" / "openrouter_key_limits.json"

        exit_code = free_caps.main(argv=["probe-openrouter", "--from-file", str(fixture_path)])

        assert exit_code == 0, f"Expected exit 0, got {exit_code}"

        # Check file written
        caps_path = codex_dir / "free-caps.json"
        assert caps_path.exists(), "free-caps.json should be written by CLI"

        captured = capsys.readouterr()
        assert "sk-or-" not in captured.out, "API key pattern in CLI output stdout"
        assert "sk-or-" not in captured.err, "API key pattern in CLI output stderr"


class TestProbeOpenRouterFreeTier:
    """Test free-tier detection in probe_openrouter."""

    def test_probe_detects_free_tier(self, hermetic, tmp_path):
        """probe_openrouter derives cap 50 for free tier."""
        from agents_inc import free_caps

        codex_dir = tmp_path / ".codex-bridge"
        codex_dir.mkdir()

        # Fixture has is_free_tier indicator
        fixture_path = Path(__file__).parent / "fixtures" / "012" / "openrouter_key_limits.json"
        result = free_caps.probe_openrouter(from_file=str(fixture_path))

        caps_path = codex_dir / "free-caps.json"
        with open(caps_path) as f:
            caps_data = json.load(f)

        # Free tier should have 50/day cap
        assert caps_data["openrouter"]["cap"] == 50
