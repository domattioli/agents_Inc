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
    r = brief(FIX / fixture / source_file, fixture, mode, workspace, available={worker_provider} if worker_tier == "frontier" else {"claude", "codex"},
              runner=runner, worker_tier=worker_tier, review_enabled=(worker_tier != "frontier"))
    rc = r.receipt
    return {"fixture": fixture, "provider": worker_provider, "tier": worker_tier,
            "model": r.route.model if r.route else None, "status": r.status,
            "checked": rc.get("checked"), "matched": rc.get("matched"),
            "reviewer": rc.get("reviewer", {}).get("status", "disabled"), "seconds": round(time.time() - t0, 1),
            "accepted": r.status in {"verified", "needs-review"} and rc.get("source_integrity") == "pass"}

def summarize(rows: list[dict]) -> str:
    out = ["# Bench — measured pilot (D5/D10)", "", "| fixture | provider/tier | model | status | quotes | reviewer | seconds | accepted |", "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        out.append(f"| {r['fixture']} | {r['provider']}/{r['tier']} | {r['model']} | {r['status']} | {r['matched']}/{r['checked']} | {r['reviewer']} | {r['seconds']} | {r['accepted']} |")
    agg = defaultdict(lambda: {"n": 0, "acc": 0, "sec": 0.0})
    for r in rows:
        k = f"{r['provider']}/{r['tier']}"; agg[k]["n"] += 1; agg[k]["acc"] += int(r["accepted"]); agg[k]["sec"] += r["seconds"]
    out += ["", "## Per configuration"]
    for k, v in agg.items():
        out.append(f"- {k}: accepted {v['acc']}/{v['n']}; mean seconds {v['sec']/v['n']:.1f}; incremental dollars: 0 (subscription only, D9); subscription calls: {v['n'] * (2 if k.endswith('cheap') else 1)}")
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
