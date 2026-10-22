# csv2json

Build a command-line tool `csv2json.py` (Python 3.10+, standard library only) in this directory.

## Behaviour

R1. `python3 csv2json.py <file.csv>` reads a CSV file whose first row is the header and prints a JSON array of objects, one per data row, keyed by header name, to stdout. Exit 0.

R2. `--indent N` pretty-prints with N spaces. Without it, output is compact (no spaces after `,` or `:`).

R3. `--types` converts values: a value that is a valid base-10 integer becomes a JSON integer, a valid decimal float becomes a JSON number, the exact strings `true` and `false` become booleans, an empty field becomes `null`. Everything else stays a string. Without `--types`, every value is a string, including empty fields (`""`).

R4. `--select a,b` outputs only the named columns, in the order given.[^1]

R5. Quoted fields follow RFC 4180: commas, double quotes (escaped as `""`) and newlines inside quotes are part of the value.

R6. Errors: a missing file, or a data row with a different number of fields than the header, prints one line starting with `error:` to stderr and exits 2. Nothing is printed to stdout.

[^1]: A name in `--select` that is not in the header is an error under R6 (exit 2), not silently skipped.

## Deliverables

1. `csv2json.py`.
2. A test suite under `tests/` that covers every requirement above, runnable with `python3 -m unittest discover -s tests`, passing.
3. `VERIFICATION.md`: for each of R1 to R6, the test(s) that cover it and the exact command you ran with its exit code. State anything you could not verify.
