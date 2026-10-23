# build-test-verify fixtures

Generic tasks for the token savings test (`docs/proposals/delegation-savings-test.md`). Each size has:

- `SPEC.md`: the only file copied into the trial's empty working directory.
- `hidden/acceptance.py`: the independent judge. It is never copied into the trial directory. The harness runs it after the session ends: `python3 hidden/acceptance.py <trial dir>`. Exit 0 means every case passed; it prints one JSON line with counts.
- Seeded traps, named in the acceptance script, form the quality floor (D5).

Only S exists so far. M and L follow once the harness has been dry-run on S.
