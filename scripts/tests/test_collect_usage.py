import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
COLLECTOR = REPO_ROOT / "scripts" / "statusline.d" / "collect_usage.py"
FIXTURES = REPO_ROOT / "scripts" / "tests" / "fixtures"


def load_jsonl(path):
    with open(path) as f:
        return [json.loads(line) for line in f]


def run_collector(args, env=None):
    cmd = [sys.executable, str(COLLECTOR)] + args
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    result = subprocess.run(cmd, capture_output=True, text=True, env=merged_env)
    return result


@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp)


@pytest.fixture
def usage_db(temp_dir):
    db_path = temp_dir / "usage.db"
    sql = (FIXTURES / "usage_fixture.sql").read_text()
    conn = sqlite3.connect(db_path)
    conn.executescript(sql)
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def prices_file(temp_dir):
    p = temp_dir / "prices.json"
    p.write_text((FIXTURES / "prices_fixture.json").read_text())
    return p


@pytest.fixture
def codex_dir(temp_dir):
    codex_root = temp_dir / "codex" / "sessions" / "a" / "b" / "c"
    codex_root.mkdir(parents=True)
    rollout = codex_root / "rollout.jsonl"
    rollout.write_text((FIXTURES / "codex_rollout.jsonl").read_text())
    # Create 2 older files to test "3 newest by mtime"
    for i in range(2):
        old = codex_root / f"old_{i}.jsonl"
        old.write_text('{"timestamp":"2026-09-05T22:00:00.000Z","type":"event_msg","payload":{"type":"token_count","rate_limits":{}}}\n')
        time.sleep(0.01)
    return temp_dir / "codex"


@pytest.fixture
def transcript_file(temp_dir):
    t = temp_dir / "transcript.jsonl"
    t.write_text((FIXTURES / "transcript_fixture.jsonl").read_text())
    return t


@pytest.fixture
def config_file(temp_dir, usage_db, prices_file, codex_dir):
    cfg = {
        "codex_config_toml": "",
        "openai_price_estimates": {"gpt-5.6-sol": "claude-opus-5"},
        "subscriptions": {"claude": 100, "openai": 100},
        "prices_json": [str(prices_file)],
        "usage_db": str(usage_db),
        "codex_sessions_glob": str(codex_dir / "**" / "*.jsonl"),
        "cache_path": str(temp_dir / "cache.json"),
        "cache_ttl_s": 60,
    }
    cfg_path = temp_dir / "config.json"
    cfg_path.write_text(json.dumps(cfg))
    return cfg_path


def test_collector_happy_path(temp_dir, config_file, transcript_file, usage_db, prices_file, codex_dir):
    cache_path = temp_dir / "cache.json"
    session_id = "test-session-123"
    session_start = 1788600000
    now = 1788651000  # 2026-09-05T23:30:00Z

    args = [
        "--session-id", session_id,
        "--transcript", str(transcript_file),
        "--session-start", str(session_start),
        "--config", str(config_file),
        "--out", str(cache_path),
        "--now", str(now),
        "--codex-glob", str(codex_dir / "**" / "*.jsonl"),
        "--usage-db", str(usage_db),
        "--prices", str(prices_file),
        "--force",
    ]

    result = run_collector(args)
    assert result.returncode == 0, f"stderr: {result.stderr}"

    out = json.loads(result.stdout)
    assert out["schema"] == 1
    assert out["session_id"] == session_id
    assert out["generated_at"] == now

    # codex assertions
    assert out["codex"]["h5"]["used_pct"] == 87.0
    assert out["codex"]["h5"]["resets_at"] == 1788669699
    assert out["codex"]["d7"]["used_pct"] == 29.0
    assert out["codex"]["d7"]["resets_at"] == 1789238480
    assert out["codex"]["observed_at"] == 1788651000

    # models assertions
    models = out["models"]
    # claude-fable-5-1: 2 unique messages (msg_a deduplicated), each 100+50+1000+200 = 1350 tokens
    fab = models["claude-fable-5-1"]
    assert fab["label"] == "Fable 5.1"
    assert fab["provider"] == "claude"
    assert fab["session"]["tokens"] == 2700  # 2 * 1350
    assert fab["session"]["tokens_noncache"] == 700  # 2 * (100 + 50 + 200): cache reads excluded
    expected_fab_cost = 2 * (100*10 + 50*50 + 1000*0.25 + 200*12.5) / 1_000_000
    assert abs(fab["session"]["cost"] - expected_fab_cost) < 1e-9

    # haiku: strip -20251001 suffix, lookup claude-haiku-4-5
    hai = models["claude-haiku-4-5"]
    assert hai["label"] == "Haiku 4.5"
    assert hai["provider"] == "claude"
    assert hai["session"]["tokens"] == 15  # 10+5+0+0
    assert hai["session"]["tokens_noncache"] == 15
    expected_hai_cost = (10*1 + 5*5) / 1_000_000
    assert abs(hai["session"]["cost"] - expected_hai_cost) < 1e-9

    # OpenAI estimate maps SOL to the Opus ladder at runtime.
    sol = models["gpt-5.6-sol"]
    assert sol["d7"]["tokens"] == 2500
    assert sol["d7"]["cost"] == pytest.approx((2000*5 + 500*25) / 1_000_000)

    # openai_total_d7 includes codex rows (gpt-5.6-sol 2500 + NULL model 3000 = 5500)
    assert out["openai_total_d7"]["tokens"] == 5500
    assert out["openai_total_d7"]["requests"] == 2  # two codex rows in 7d window

    # free_top4_d7 ranks by all-time tokens: old 2020 gemini-old 999999 (7D 0), nemotron 9000, codestral 7000,
    # gemini-3.8-flash 5000; ministral (10) drops out
    free_top4 = out["free_top4_d7"]
    assert [e["model"] for e in free_top4] == ["gemini-old", "nvidia/nemotron-3-ultra-550b-a55b:free", "codestral-latest", "gemini-3.8-flash"]
    assert free_top4[0]["all"]["tokens"] == 999999
    assert free_top4[0]["tokens"] == 0 and free_top4[0]["d7"]["tokens"] == 0 and free_top4[0]["session"]["tokens"] == 0
    assert free_top4[1] == {
        "backend": "openrouter", "model": "nvidia/nemotron-3-ultra-550b-a55b:free", "tokens": 9000,
        "session": {"tokens": 9000, "cost": None, "equiv_cost": pytest.approx(0.009)}, "d7": {"tokens": 9000, "cost": None, "equiv_cost": pytest.approx(0.009)},
        "h5": {"tokens": 9000, "equiv_cost": pytest.approx(0.009)}, "d1": {"tokens": 9000, "equiv_cost": pytest.approx(0.009)},
        "d28": {"tokens": 9000, "equiv_cost": pytest.approx(0.009)}, "all": {"tokens": 9000, "equiv_cost": pytest.approx(0.009)},
    }
    assert free_top4[2] == {
        "backend": "mistral", "model": "codestral-latest", "tokens": 7000,
        "session": {"tokens": 7000, "cost": None, "equiv_cost": pytest.approx(0.007)}, "d7": {"tokens": 7000, "cost": None, "equiv_cost": pytest.approx(0.007)},
        "h5": {"tokens": 7000, "equiv_cost": pytest.approx(0.007)}, "d1": {"tokens": 7000, "equiv_cost": pytest.approx(0.007)},
        "d28": {"tokens": 7000, "equiv_cost": pytest.approx(0.007)}, "all": {"tokens": 7000, "equiv_cost": pytest.approx(0.007)},
    }
    assert free_top4[3] == {
        "backend": "gemini", "model": "gemini-3.8-flash", "tokens": 5000,
        "session": {"tokens": 5000, "cost": None, "equiv_cost": pytest.approx(0.005)}, "d7": {"tokens": 5000, "cost": None, "equiv_cost": pytest.approx(0.005)},
        "h5": {"tokens": 5000, "equiv_cost": pytest.approx(0.005)}, "d1": {"tokens": 5000, "equiv_cost": pytest.approx(0.005)},
        "d28": {"tokens": 5000, "equiv_cost": pytest.approx(0.005)}, "all": {"tokens": 5000, "equiv_cost": pytest.approx(0.005)},
    }

    # free_windows: all 3 fixture rows are inside the 28d window; old 2020 row excluded
    assert out["free_windows"]["d28"]["tokens"] == 21010
    assert set(out["free_windows"]) == {"session", "today", "d7", "d28"}

    # All schema keys present
    required_keys = {
        "schema", "session_id", "generated_at", "codex", "models",
        "model_pins", "openai_total_d7", "claude_d7", "claude_today", "openai_today", "claude_h5", "openai_h5", "free_top4_d7", "cum_use",
        "claude_all", "openai_all", "free_all", "history_days", "free_windows", "provider_windows", "cache_pct",
        "session_list_cost", "sub_ratio_d7", "blended_usd_per_mtok_d7"
    }
    assert set(out.keys()) == required_keys
    assert set(out["codex"].keys()) == {"h5", "d7", "observed_at"}
    for window in ("h5", "d7"):
        assert set(out["codex"][window].keys()) == {"used_pct", "resets_at"}
    for model_info in out["models"].values():
        assert set(model_info.keys()) == {"label", "provider", "session", "h5", "d1", "d7", "d28", "all"}
        assert set(model_info["session"].keys()) == {"tokens", "tokens_noncache", "cost"}
        assert set(model_info["d7"].keys()) == {"tokens", "cost"}
        assert set(model_info["d28"].keys()) == {"tokens", "cost"}
        assert model_info["d28"]["tokens"] >= model_info["d7"]["tokens"]
    # d28 ("Mo") window: sonnet has 1M in 7d plus 500k twenty days ago.
    son = out["models"]["claude-sonnet-5"]
    assert son["d7"]["tokens"] == 1000000
    assert son["d28"]["tokens"] == 1500000
    assert son["d28"]["cost"] == pytest.approx(4.5)
    # cum_use: every row ever, Anthropic-API-equivalent pricing (free -> haiku, null codex -> sonnet).
    assert set(out["cum_use"].keys()) == {"tokens", "cost"}
    assert out["cum_use"]["tokens"] == 2526659
    assert out["cum_use"]["cost"] == pytest.approx(5.552859, abs=1e-4)
    assert out["claude_today"] == {"tokens": 1000150, "cost": pytest.approx(3.00035)}
    assert out["openai_today"] == {"tokens": 5500, "cost": pytest.approx(0.0225)}
    # claude_all/openai_all/free_all: same provider classification and cost
    # model as today/h5 blocks, no time filter (all-time totals).
    assert set(out["claude_all"].keys()) == {"tokens", "cost"}
    assert out["claude_all"]["tokens"] == 1500150
    assert out["claude_all"]["cost"] == pytest.approx(4.50035)
    assert set(out["openai_all"].keys()) == {"tokens", "cost"}
    assert out["openai_all"]["tokens"] == 5500
    assert out["openai_all"]["cost"] == pytest.approx(0.0225)
    assert set(out["free_all"].keys()) == {"tokens", "equiv_cost"}
    assert out["free_all"]["tokens"] == 1021009
    assert out["free_all"]["equiv_cost"] == pytest.approx(1.021009, abs=1e-4)
    # claude_all + openai_all + free_all tokens must equal cum_use tokens.
    assert (out["claude_all"]["tokens"] + out["openai_all"]["tokens"]
            + out["free_all"]["tokens"]) == out["cum_use"]["tokens"]
    assert set(out["openai_total_d7"].keys()) == {"tokens", "requests"}
    # provider_windows: provider totals; reuses the claude accumulators, d28 is new.
    pw = out["provider_windows"]
    assert set(pw.keys()) == {"claude", "openai", "free"}
    for prov in pw.values():
        assert set(prov.keys()) == {"h5", "d1", "d7", "d28", "all"}
        for cell in prov.values():
            assert set(cell.keys()) == {"tokens", "cost"}
        assert prov["d28"]["tokens"] >= prov["d7"]["tokens"]
        assert prov["all"]["tokens"] >= prov["d28"]["tokens"]
    assert pw["claude"]["h5"]["tokens"] == out["claude_h5"]["tokens"]
    assert pw["claude"]["d1"]["tokens"] == out["claude_today"]["tokens"]
    assert pw["claude"]["d7"]["tokens"] == out["claude_d7"]["tokens"]
    assert pw["claude"]["d7"]["cost"] == out["claude_d7"]["cost"]
    assert pw["claude"]["all"]["tokens"] == out["claude_all"]["tokens"]
    assert pw["openai"]["d7"]["tokens"] == out["openai_total_d7"]["tokens"]
    assert pw["openai"]["all"]["tokens"] == out["openai_all"]["tokens"]
    assert pw["free"]["d28"]["tokens"] == out["free_windows"]["d28"]["tokens"]
    assert pw["free"]["h5"]["tokens"] is None
    assert set(out["claude_d7"].keys()) == {"tokens", "cost"}
    assert set(out["claude_today"].keys()) == {"tokens", "cost"}
    assert set(out["openai_today"].keys()) == {"tokens", "cost"}
    assert set(out["sub_ratio_d7"].keys()) == {"claude", "openai"}
    assert set(out["blended_usd_per_mtok_d7"].keys()) == {"claude", "openai"}


def test_missing_usage_db_exits_zero(temp_dir, config_file, transcript_file, prices_file, codex_dir):
    cache_path = temp_dir / "cache.json"
    missing_db = temp_dir / "missing.db"

    args = [
        "--session-id", "test",
        "--transcript", str(transcript_file),
        "--session-start", "1788600000",
        "--config", str(config_file),
        "--out", str(cache_path),
        "--now", "1788651000",
        "--codex-glob", str(codex_dir / "**" / "*.jsonl"),
        "--usage-db", str(missing_db),
        "--prices", str(prices_file),
        "--force",
    ]

    result = run_collector(args)
    assert result.returncode == 0
    out = json.loads(result.stdout)
    assert out["free_top4_d7"] == []


def test_ttl_cache_skips_recollect(temp_dir, config_file, transcript_file, usage_db, prices_file, codex_dir):
    cache_path = temp_dir / "cache.json"
    session_id = "ttl-test"
    session_start = 1788600000
    now = 1788651000

    args = [
        "--session-id", session_id,
        "--transcript", str(transcript_file),
        "--session-start", str(session_start),
        "--config", str(config_file),
        "--out", str(cache_path),
        "--now", str(now),
        "--codex-glob", str(codex_dir / "**" / "*.jsonl"),
        "--usage-db", str(usage_db),
        "--prices", str(prices_file),
        "--force",
    ]

    # First run
    result1 = run_collector(args)
    assert result1.returncode == 0
    mtime1 = cache_path.stat().st_mtime

    # Second run immediately (within TTL, no --force)
    args_no_force = [a for a in args if a != "--force"]
    result2 = run_collector(args_no_force)
    assert result2.returncode == 0
    mtime2 = cache_path.stat().st_mtime

    # mtime should not have changed (collector skipped)
    assert mtime2 == mtime1, "Cache file mtime changed; collector did not respect TTL"


def test_premium_only_rollout_codex_none(temp_dir, config_file, transcript_file, usage_db, prices_file):
    # Create codex dir with only premium limit_id
    codex_root = temp_dir / "codex_premium" / "sessions" / "a" / "b" / "c"
    codex_root.mkdir(parents=True)
    rollout = codex_root / "rollout.jsonl"
    rollout.write_text('{"timestamp":"2026-09-05T23:30:00.000Z","type":"event_msg","payload":{"type":"token_count","rate_limits":{"limit_id":"premium","primary":null,"secondary":null}}}\n')

    cache_path = temp_dir / "cache.json"
    session_id = "premium-test"
    session_start = 1788600000
    now = 1788651000

    args = [
        "--session-id", session_id,
        "--transcript", str(transcript_file),
        "--session-start", str(session_start),
        "--config", str(config_file),
        "--out", str(cache_path),
        "--now", str(now),
        "--codex-glob", str(codex_root / "**" / "*.jsonl"),
        "--usage-db", str(usage_db),
        "--prices", str(prices_file),
        "--force",
    ]

    result = run_collector(args)
    assert result.returncode == 0
    out = json.loads(result.stdout)
    assert out["codex"]["h5"]["used_pct"] is None
    assert out["codex"]["d7"]["used_pct"] is None
    assert out["codex"]["observed_at"] is None


def test_model_version_normalization_d7(temp_dir, config_file, transcript_file, usage_db, prices_file, codex_dir):
    # Test that model id with -YYYYMMDD suffix is normalized before d7 aggregation
    cache_path = temp_dir / "cache.json"
    session_id = "version-norm-test"
    session_start = 1788600000
    now = 1788651000

    args = [
        "--session-id", session_id,
        "--transcript", str(transcript_file),
        "--session-start", str(session_start),
        "--config", str(config_file),
        "--out", str(cache_path),
        "--now", str(now),
        "--codex-glob", str(codex_dir / "**" / "*.jsonl"),
        "--usage-db", str(usage_db),
        "--prices", str(prices_file),
        "--force",
    ]

    result = run_collector(args)
    assert result.returncode == 0, f"stderr: {result.stderr}"

    out = json.loads(result.stdout)
    models = out["models"]

    # claude-haiku-4-5 should include d7 tokens from the versioned row (claude-haiku-4-5-20251001: 100+50+0+0=150)
    hai = models["claude-haiku-4-5"]
    assert hai["d7"]["tokens"] == 150, f"Expected 150 tokens for claude-haiku-4-5 d7, got {hai['d7']['tokens']}"
    # cost should be numeric (not null)
    assert hai["d7"]["cost"] is not None, f"Expected numeric cost for claude-haiku-4-5 d7, got {hai['d7']['cost']}"
    assert isinstance(hai["d7"]["cost"], (int, float)), f"Expected numeric cost, got {type(hai['d7']['cost'])}"


def test_free_top4_session_and_d7_fields(temp_dir, config_file, transcript_file, usage_db, prices_file, codex_dir):
    """free_top4_d7 entries carry session/d7 token+cost blocks (T4)."""
    cache_path = temp_dir / "cache.json"
    args = [
        "--session-id", "free-fields",
        "--transcript", str(transcript_file),
        # Session window starts well after the fixture's older rows but before the -1h rows.
        "--session-start", "1788600000",
        "--config", str(config_file),
        "--out", str(cache_path),
        "--now", "1788651000",
        "--codex-glob", str(codex_dir / "**" / "*.jsonl"),
        "--usage-db", str(usage_db),
        "--prices", str(prices_file),
        "--force",
    ]
    result = run_collector(args)
    assert result.returncode == 0, f"stderr: {result.stderr}"
    out = json.loads(result.stdout)

    for entry in out["free_top4_d7"]:
        assert set(entry.keys()) == {"backend", "model", "tokens", "session", "d7", "h5", "d1", "d28", "all"}
        assert set(entry["session"].keys()) == {"tokens", "cost", "equiv_cost"}
        assert set(entry["d7"].keys()) == {"tokens", "cost", "equiv_cost"}
        # Free tier is unpriced, but the API-equivalent estimate (haiku tier) is numeric.
        assert entry["d7"]["equiv_cost"] == pytest.approx(entry["d7"]["tokens"] / 1_000_000)
        assert entry["d7"]["tokens"] == entry["tokens"]
        assert isinstance(entry["session"]["tokens"], int)
        # Fixture free rows are all inside the session window.
        assert entry["session"]["tokens"] == entry["d7"]["tokens"]
        # No prices exist for the free backends -> cost is null (renderer shows "$0").
        assert entry["session"]["cost"] is None
        assert entry["d7"]["cost"] is None


def test_free_top4_session_zero_outside_window(temp_dir, config_file, transcript_file, usage_db, prices_file, codex_dir):
    """A session window in the future yields zero session tokens but intact d7 tokens (rows inside 7D)."""
    cache_path = temp_dir / "cache.json"
    future = 4102444800  # 2100-01-01
    args = [
        "--session-id", "free-future",
        "--transcript", str(transcript_file),
        "--session-start", str(future),
        "--config", str(config_file),
        "--out", str(cache_path),
        "--now", "1788651000",
        "--codex-glob", str(codex_dir / "**" / "*.jsonl"),
        "--usage-db", str(usage_db),
        "--prices", str(prices_file),
        "--force",
    ]
    result = run_collector(args)
    assert result.returncode == 0, f"stderr: {result.stderr}"
    out = json.loads(result.stdout)
    assert out["free_top4_d7"], "expected free entries"
    for entry in out["free_top4_d7"]:
        assert entry["session"]["tokens"] == 0
        if entry["model"] != "gemini-old":  # 2020 row: outside 7D, shown by all-time rank
            assert entry["d7"]["tokens"] > 0


def test_absent_sources_give_null_not_zero(temp_dir, config_file, transcript_file, prices_file, codex_dir):
    """Unknown is not zero: a missing usage db leaves OpenAI session and window tokens null."""
    cache_path = temp_dir / "cache.json"
    args = [
        "--session-id", "test",
        "--transcript", str(transcript_file),
        "--session-start", "1788600000",
        "--config", str(config_file),
        "--out", str(cache_path),
        "--now", "1788651000",
        "--usage-db", str(temp_dir / "missing.db"),
        "--prices", str(prices_file),
        "--force",
    ]
    result = run_collector(args)
    assert result.returncode == 0
    out = json.loads(result.stdout)
    oai = [m for m in out["models"].values() if m["provider"] == "openai"]
    assert oai
    for m in oai:
        assert m["session"]["tokens"] is None
        assert m["session"]["tokens_noncache"] is None
        assert m["d7"]["tokens"] is None
    claude = [m for m in out["models"].values() if m["provider"] == "claude"]
    assert any(m["session"]["tokens"] is not None for m in claude)


def test_claude_windows_null_without_usage_db_even_with_state_db(temp_dir, config_file, transcript_file, prices_file):
    """Claude windows come from usage.db only: a Codex state db must not make them look known."""
    import sqlite3 as _s
    state = temp_dir / "state_5.sqlite"
    _s.connect(state).close()
    cfg = json.loads(config_file.read_text()); cfg["codex_state_db"] = str(state)
    config_file.write_text(json.dumps(cfg))
    args = ["--session-id", "test", "--transcript", str(transcript_file), "--session-start", "1788600000",
            "--config", str(config_file), "--out", str(temp_dir / "c.json"), "--now", "1788651000",
            "--usage-db", str(temp_dir / "missing.db"), "--prices", str(prices_file), "--force"]
    out = json.loads(run_collector(args).stdout)
    for m in out["models"].values():
        if m["provider"] == "claude":
            assert m["d7"]["tokens"] is None


def test_history_days_plausible(temp_dir, config_file, transcript_file, usage_db, prices_file, codex_dir):
    """history_days = now - earliest usage row per provider, uncapped (real clock, fixture rows are relative to it)."""
    cache_path = temp_dir / "cache.json"
    args = [
        "--session-id", "hist-1",
        "--transcript", str(transcript_file),
        "--config", str(config_file),
        "--out", str(cache_path),
        "--codex-glob", str(codex_dir / "**" / "*.jsonl"),
        "--usage-db", str(usage_db),
        "--prices", str(prices_file),
        "--force",
    ]
    result = run_collector(args)
    assert result.returncode == 0, f"stderr: {result.stderr}"
    h = json.loads(cache_path.read_text())["history_days"]
    assert set(h) == {"claude", "openai", "free"}
    # claude: oldest fixture row is 20 days old
    assert 19.9 < h["claude"] < 20.1
    # openai: oldest fixture row is 1 hour old
    assert 0.0 < h["openai"] < 0.1
    # free: 2020 gemini row, uncapped (well beyond 28 days)
    assert h["free"] > 2000


def _seed_ranking_db(path, rows):
    conn = sqlite3.connect(path)
    conn.executescript((FIXTURES / "usage_fixture.sql").read_text().split("INSERT")[0])
    for i, (backend, model, tok) in enumerate(rows):
        conn.execute(
            "INSERT INTO usage(uid,ts,day,backend,model,input_tokens,output_tokens) VALUES (?,?,date('now','localtime'),?,?,?,0)",
            ("r%d" % i, "2026-10-01T00:00:00.000+00:00", backend, model, tok))
    conn.commit()
    conn.close()


def _run_rank(temp_dir, rows, toml_text=None, claude_model=""):
    db = temp_dir / "rank.db"
    db.unlink(missing_ok=True)
    _seed_ranking_db(db, rows)
    cfg = {"usage_db": str(db), "codex_state_db": "", "prices_json": [], "cache_path": str(temp_dir / "rc.json"),
           "codex_sessions_glob": str(temp_dir / "none" / "*.jsonl"), "codex_config_toml": ""}
    if toml_text is not None:
        toml = temp_dir / "config.toml"
        toml.write_text(toml_text)
        cfg["codex_config_toml"] = str(toml)
    cfg_path = temp_dir / "rank_config.json"
    cfg_path.write_text(json.dumps(cfg))
    args = ["--session-id", "s", "--config", str(cfg_path), "--out", str(temp_dir / "rc.json"), "--force"]
    if claude_model:
        args += ["--current-claude-model", claude_model]
    r = run_collector(args)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_rows_are_top4_exact_versions_by_all_tokens(temp_dir):
    rows = [("claude", "claude-sonnet-5", 900), ("claude", "claude-opus-5", 800), ("claude", "claude-opus-5-5", 700),
            ("claude", "claude-haiku-4-5-20251001", 600), ("claude", "claude-fable-5-1", 500), ("claude", "claude-fable-5", 400),
            ("codex", "gpt-5.6-sol", 90), ("codex", "gpt-5.6-luna", 80), ("codex", "gpt-5.6-terra", 70),
            ("codex", "gpt-6-astra", 60), ("codex", "gpt-5.5", 50)]
    out = _run_rank(temp_dir, rows)
    ids = list(out["models"])
    assert ids[:4] == ["claude-sonnet-5", "claude-opus-5", "claude-opus-5-5", "claude-haiku-4-5"]
    assert ids[4:] == ["gpt-5.6-sol", "gpt-5.6-luna", "gpt-5.6-terra", "gpt-6-astra"]
    assert out["models"]["gpt-5.6-sol"]["all"]["tokens"] == 90
    assert out["models"]["claude-opus-5"]["all"]["tokens"] == 800
    assert out["models"]["claude-opus-5-5"]["all"]["tokens"] == 700
    assert out["models"]["claude-opus-5-5"]["label"] == "Opus 5.5"
    assert out["models"]["claude-opus-5"]["label"] == "Opus 5"
    assert out["models"]["gpt-5.6-luna"]["label"] == "GPT-5.6 Luna"
    assert "gpt-6-sol" not in out["models"]


def test_current_model_outside_top4_takes_row4(temp_dir):
    rows = [("claude", "claude-sonnet-5", 900), ("claude", "claude-opus-5", 800), ("claude", "claude-opus-5-5", 700),
            ("claude", "claude-haiku-4-5", 600), ("claude", "claude-fable-5-1", 500),
            ("codex", "gpt-5.6-sol", 50), ("codex", "gpt-5.6-luna", 80), ("codex", "gpt-5.6-terra", 70),
            ("codex", "gpt-6-astra", 60), ("codex", "gpt-5.5", 90)]
    out = _run_rank(temp_dir, rows, toml_text='model = "gpt-5.6-sol"\nmodel_reasoning_effort = "low"\n[projects.x]\nmodel = "other"\n',
                    claude_model="claude-fable-5-1[1m]")
    ids = list(out["models"])
    assert ids[:4] == ["claude-sonnet-5", "claude-opus-5", "claude-opus-5-5", "claude-fable-5-1"]
    assert ids[4:] == ["gpt-5.5", "gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol"]
    assert out["model_pins"] == {"claude": "claude-fable-5-1", "openai": "gpt-5.6-sol"}
    # Pin already inside the top 4 keeps its rank.
    out = _run_rank(temp_dir, rows, toml_text='model = "gpt-5.5"\n', claude_model="claude-opus-5")
    assert list(out["models"])[:4] == ["claude-sonnet-5", "claude-opus-5", "claude-opus-5-5", "claude-haiku-4-5"]
    assert list(out["models"])[4] == "gpt-5.5"


def test_model_label_and_normalize():
    sys.path.insert(0, str(COLLECTOR.parent))
    import collect_usage as cu
    assert cu.model_label("claude-haiku-4-5-20251001") == "Haiku 4.5"
    assert cu.model_label("claude-sonnet-5") == "Sonnet 5"
    assert cu.model_label("gpt-6-astra") == "GPT-6 Astra"
    assert cu.model_label("gpt-5.6-terra") == "GPT-5.6 Terra"
    assert cu.normalize_model("claude-opus-5-5") == "claude-opus-5-5"
    assert cu.normalize_model("sol") == "sol"
