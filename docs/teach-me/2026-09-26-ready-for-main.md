# Are we ready for main?

## 1. The rule

- **Pushing straight to main:** not allowed in this repository. Changes reach `main` only through a pull request from `development`. Evidence: `AGENTS.md:92`.
- **Owner exception:** the operator owns the repo and can waive the PR rule for one push. The waiver covers this push only. The no-force-push rule still holds.

## 2. Can git take the push?

- **Not yet.** `origin/main` has commit `1c93330` (squash-merge of PR #40) that `development` lacks. A push without it is rejected, and force push stays banned. Fix: merge `origin/main` into `development`, then push.
- **Uncommitted work:** the dispatch-checker changes are not committed, so they would not go along.

## 3. Readiness checks (no PR means no review or CI)

1. Full suite `python3 -m unittest discover -s tests -p 'test_*.py'` exits 0.
2. `git status` is clean of anything meant to ship.
3. Merge of `origin/main` into `development` has no conflicts.
4. `git log origin/main..development` lists only commits wanted on main.

## 4. Decision

- Operator chose: commit, merge main in, run the 4 checks, confirm once more, then push. Work dispatched to sol.
