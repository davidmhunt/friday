# gate-02: `friday result` records an expensive run once so Verify stays cheap
Status: approved
Goal: v1-final
Node: any
Deliverable: code
Land: goal
Verify: uv run --with pytest pytest -q tests/test_result.py && uv run --with pytest pytest -q && claude plugin validate .
Hardware: none

## Goal
A training run, sweep or bench test runs once as a step and is recorded in a tracked file
`results/<id>.json`; the directive's Verify is `friday result check <id> ...`, which takes
seconds and can be repeated at every fix round and at landing. tests/test_result.py proves the
record and each way the check fails.

## Steps
1. `friday result write <id> [--metric K=V]... [--file PATH]... [--cmd TEXT] [--note TEXT]`
   (new lib/friday_result.py): writes `results/<id>.json` with the metrics, each file's sha256
   and size, the command, the HEAD commit, whether the tree was dirty, the node name and the
   time. Files may be untracked (datasets, checkpoints under `runs/`); the record is tracked.
2. `friday result check <id> [--require 'K OP V']... [--files]`: exit 0 only when the record
   exists, its commit is an ancestor of HEAD, every `--require` holds (`>= > <= < == !=`, numeric
   or string), and with `--files` every recorded file that is present still has its hash. Prints
   one line per failed condition; exit 1 otherwise.
3. `friday check`: warn when a directive's Verify matches a `hardware` pattern in
   `.claude/friday.json` (Verify is re-run unattended, without the hardware prompt), and point to
   `friday result`.
4. Allow rules: add `friday result *`. Help text. skills/long-jobs/SKILL.md and
   skills/data-artifacts/SKILL.md: the run-once, record, cheap-check pattern; say plainly that
   these two skills are advice and no hook enforces them. skills/plan/SKILL.md: how to choose
   Verify for an expensive or hardware run.
5. tests/test_result.py: write then check passes; missing record, unmet requirement, changed file
   and a record from an unrelated commit each fail with a clear line; the hardware warning.
   CHANGELOG.

## Out of scope
- A second Verify field, caching Verify results, and uploading result files anywhere.

## Log
