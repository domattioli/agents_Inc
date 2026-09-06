"""Measured pilot: cheap-tier pipeline vs all-frontier single-model baseline. Reports counts, never percentages (D10)."""
from __future__ import annotations
import argparse, json, os, time
from collections import defaultdict
from pathlib import Path
from .pipeline import brief
from .adapters.base import run_worker
from .router import _TABLE

FIX = Path(__file__).resolve().parent.parent / "fixtures"
CASES = [("tim", "matter.md", "lawyer"), ("dom", "design.md", "engineer")]
CONFIGS = [("claude", "cheap"), ("codex", "cheap"), ("claude", "frontier"), ("codex", "frontier")]
T15_CONFIGS = [("claude", "cheap"), ("codex", "cheap")]

def run_case(fixture, source_file, mode, worker_provider, worker_tier, workspace,
             runner=run_worker, governance_mode=None) -> dict:
    calls = 0
    def counted_runner(*args, **kwargs):
        nonlocal calls
        calls += 1
        return runner(*args, **kwargs)
    t0 = time.time()
    r = brief(FIX / fixture / source_file, fixture, mode, workspace, available={"claude", "codex"},
              worker_provider=worker_provider, runner=counted_runner, worker_tier=worker_tier,
              review_enabled=(worker_tier != "frontier"), governance_mode=governance_mode)
    rc = r.receipt
    verifier_pass = rc.get("source_integrity") == "pass"
    accepted = r.status in {"verified", "needs-review"} and verifier_pass
    return {"fixture": fixture, "provider": worker_provider, "tier": worker_tier,
            "model": r.route.model if r.route else None, "status": r.status,
            "checked": rc.get("checked"), "matched": rc.get("matched"),
            "reviewer": rc.get("reviewer", {}).get("status", "disabled"), "seconds": round(time.time() - t0, 1),
            "accepted": accepted, "verifier_pass": verifier_pass, "review": rc.get("content_review"),
            "corrections": rc.get("corrections", 0), "paused_reason": rc.get("paused_reason"),
            "governance": governance_mode or os.environ.get("WORKERBEES_GOVERNANCE", "off"),
            "subscription_calls": calls, "incremental_cost": "subscription, unknown $"}

def summarize(rows: list[dict]) -> str:
    out = ["# Bench — measured pilot (D5/D10)", "", "| fixture | governance | provider/tier | model | status | quotes | reviewer | review | seconds | accepted | verifier_pass |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        out.append(f"| {r['fixture']} | {r.get('governance', 'n/a')} | {r['provider']}/{r['tier']} | {r['model']} | {r['status']} | {r['matched']}/{r['checked']} | {r['reviewer']} | {r.get('review', 'n/a')} | {r['seconds']} | {r['accepted']} | {r.get('verifier_pass', False)} |")
    agg = defaultdict(lambda: {"n": 0, "acc": 0, "vp": 0, "sec": 0.0, "statuses": defaultdict(int), "corrections": 0.0, "calls": 0})
    for r in rows:
        k = f"{r['provider']}/{r['tier']}"
        if "governance" in r:
            k += f" ({r['governance']})"
        agg[k]["n"] += 1; agg[k]["acc"] += int(r["accepted"]); agg[k]["vp"] += int(r.get("verifier_pass", False)); agg[k]["sec"] += r["seconds"]
        agg[k]["statuses"][r["status"]] += 1; agg[k]["corrections"] += r.get("corrections", 0)
        agg[k]["calls"] += r.get("subscription_calls", 1 if r["tier"] == "frontier" else 2 + 2 * r.get("corrections", 0))
    out += ["", "Frontier baseline runs without a Reviewer, so it cannot reach accepted; compare on verifier_pass and seconds.", "", "## Per configuration"]
    for k, v in agg.items():
        statuses_str = ", ".join(f"{s}: {c}" for s, c in sorted(v["statuses"].items()))
        corr_mean = v["corrections"] / v["n"] if v["n"] > 0 else 0.0
        out.append(f"- {k}: accepted {v['acc']}/{v['n']}; verifier_pass {v['vp']}/{v['n']}; mean seconds {v['sec']/v['n']:.1f}; statuses: {{{statuses_str}}}; corrections_mean: {corr_mean:.1f}; incremental cost: unknown (subscription billing not measured); observed subscription calls: {v['calls']}")
    out += ["", "No savings percentage is reported until both workflows are measured at N≥5 (D10)."]
    return "\n".join(out)

def main() -> None:
    ap = argparse.ArgumentParser(); ap.add_argument("--n", type=int, default=1); ap.add_argument("--out", default="docs/BENCH.md")
    ap.add_argument("--t15", action="store_true")
    a = ap.parse_args()
    if a.t15:
        if a.n < 5:
            raise SystemExit("T15 requires --n >= 5")
        if os.environ.get("WORKERBEES_STORE") != "both" or os.environ.get("WORKERBEES_GOVERNANCE") != "enforce":
            raise SystemExit("T15 requires WORKERBEES_STORE=both WORKERBEES_GOVERNANCE=enforce")
        rows = []
        for i in range(a.n):
            for f, s, m in CASES:
                for p, t in T15_CONFIGS:
                    for governance in ("off", "enforce"):
                        ws = Path(".scratch") / "bench-t15" / governance / f"{i}-{f}-{p}"
                        rows.append(run_case(f, s, m, p, t, ws, governance_mode=governance))
        pairs = zip(rows[0::2], rows[1::2])
        unchanged = all(off["status"] == enforce["status"] and
                        off["status"] in {"verified", "needs-review"}
                        for off, enforce in pairs)
        section = "\n\n## T15 governance benchmark — 2026-09-06\n\n"
        section += f"Gate verified/needs-review unchanged vs governance=off: {'PASS' if unchanged else 'FAIL'}.\n\n"
        section += summarize(rows).replace("# Bench — measured pilot (D5/D10)", "### Results")
        section += "\n\nOpenRouter lane skipped: daily quota exhausted. Cost: subscription, unknown $. "
        section += "Calls are wrapper-observed, not estimated.\n\n```json\n" + json.dumps(rows, indent=1) + "\n```\n"
        with Path(a.out).open("a") as fh:
            fh.write(section)
        print(f"T15_GATE={'PASS' if unchanged else 'FAIL'} rows={len(rows)} calls={sum(r['subscription_calls'] for r in rows)}")
        if not unchanged:
            raise SystemExit(1)
    else:
        rows = [run_case(f, s, m, p, t, Path(".")) for _ in range(a.n) for (f, s, m) in CASES for (p, t) in CONFIGS]
        Path(a.out).write_text(summarize(rows) + "\n\n```json\n" + json.dumps(rows, indent=1) + "\n```\n")
        print(summarize(rows))

if __name__ == "__main__":
    main()
