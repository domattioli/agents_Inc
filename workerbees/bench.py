"""Measured pilot: cheap-tier pipeline vs all-frontier single-model baseline. Reports counts, never percentages (D10)."""
from __future__ import annotations
import argparse, json, time
from collections import defaultdict
from pathlib import Path
from .pipeline import brief
from .adapters.base import run_worker
from .router import _TABLE

FIX = Path(__file__).resolve().parent.parent / "fixtures"
CASES = [("tim", "matter.md", "lawyer"), ("dom", "design.md", "engineer")]
CONFIGS = [("claude", "cheap"), ("codex", "cheap"), ("claude", "frontier"), ("codex", "frontier")]

def run_case(fixture, source_file, mode, worker_provider, worker_tier, workspace, runner=run_worker) -> dict:
    t0 = time.time()
    r = brief(FIX / fixture / source_file, fixture, mode, workspace, available={"claude", "codex"},
              worker_provider=worker_provider, runner=runner, worker_tier=worker_tier, review_enabled=(worker_tier != "frontier"))
    rc = r.receipt
    verifier_pass = rc.get("source_integrity") == "pass"
    accepted = r.status in {"verified", "needs-review"} and verifier_pass
    return {"fixture": fixture, "provider": worker_provider, "tier": worker_tier,
            "model": r.route.model if r.route else None, "status": r.status,
            "checked": rc.get("checked"), "matched": rc.get("matched"),
            "reviewer": rc.get("reviewer", {}).get("status", "disabled"), "seconds": round(time.time() - t0, 1),
            "accepted": accepted, "verifier_pass": verifier_pass, "review": rc.get("content_review"),
            "corrections": rc.get("corrections", 0), "paused_reason": rc.get("paused_reason"),
            "subscription_calls": 1 if worker_tier == "frontier" else 2 + 2 * rc.get("corrections", 0),
            "incremental_cost": "unknown"}

def summarize(rows: list[dict]) -> str:
    out = ["# Bench — measured pilot (D5/D10)", "", "| fixture | provider/tier | model | status | quotes | reviewer | review | seconds | accepted | verifier_pass |", "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        out.append(f"| {r['fixture']} | {r['provider']}/{r['tier']} | {r['model']} | {r['status']} | {r['matched']}/{r['checked']} | {r['reviewer']} | {r.get('review', 'n/a')} | {r['seconds']} | {r['accepted']} | {r.get('verifier_pass', False)} |")
    agg = defaultdict(lambda: {"n": 0, "acc": 0, "vp": 0, "sec": 0.0, "statuses": defaultdict(int), "corrections": 0.0, "calls": 0})
    for r in rows:
        k = f"{r['provider']}/{r['tier']}"; agg[k]["n"] += 1; agg[k]["acc"] += int(r["accepted"]); agg[k]["vp"] += int(r.get("verifier_pass", False)); agg[k]["sec"] += r["seconds"]
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
    a = ap.parse_args()
    rows = [run_case(f, s, m, p, t, Path(".")) for _ in range(a.n) for (f, s, m) in CASES for (p, t) in CONFIGS]
    Path(a.out).write_text(summarize(rows) + "\n\n```json\n" + json.dumps(rows, indent=1) + "\n```\n")
    print(summarize(rows))

if __name__ == "__main__":
    main()
