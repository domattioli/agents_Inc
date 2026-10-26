# Live-event fixtures (spec 027)

- `codex.jsonl`, `claude.jsonl`: fake provider output with planted fake secrets, one unknown event type and one non-JSON line.
- `fake_codex`, `fake_claude`: fake CLIs that print those files. Env: `FAKE_PACE` (seconds between lines, default 0.5), `FAKE_SLEEP` (sleep forever after the first line), `FAKE_RC` (exit code), `FAKE_FIXTURE` (fixture path). Tests copy them into a temp dir and mark them executable.
- `codex.rows.txt`, `claude.rows.txt`: expected rendered rows. Convention for the row tests: model `sol` for Codex and `haiku` for Claude, run id `fixture-run`, `run.start` at second 0, fixture line N at second N (the last `run.end` at second N+1 with outcome `done`, rc 0). Each fixture line yields one envelope, so row N is line N.
- `golden/`: `stdout.md`, `usage.json` and the verdict line recorded with the code before spec 027 (SC-002). Do not regenerate them.
