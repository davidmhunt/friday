# rel-02: Release 1.1.0, installed from main
Status: done
Goal: attention
Node: any
Deliverable: code
Land: goal
Verify: uv run --with pytest pytest -q tests/test_release.py && uv run --with pytest pytest -q && claude plugin validate .
Hardware: none

## Goal
The attention goal ships as friday 1.1.0: version, changelog and install instructions agree, and
now that 1.0.0 is on main (tagged `v1.0.0`) the docs clone `main`, not `v1`. Approved by the user
on 2026-11-18. tests/test_release.py proves it.

## Steps
1. .claude-plugin/plugin.json and .claude-plugin/marketplace.json: version `1.1.0`. CHANGELOG.md:
   turn `Unreleased` into `1.1.0 - <date>` with a one-line summary on top, add an empty
   `Unreleased`.
2. README.md and docs/getting-started.md: the clone line clones `main` (drop `-b v1` and the
   "until 1.0 is on main" note); docs/migrating-from-v0.md and the recipes likewise if they name
   `v1`. New goals in the examples use `Base: main`.
3. tests/test_release.py: marketplace.json's version (if it has one) equals plugin.json's; no doc
   under docs/ or README.md tells the reader to clone with `-b v1`.

## Out of scope
- Tagging, merging v1 into main, deleting `v1`: the user does these.

## Log

### 2026-11-18
Commits:
- f0fbad5 rel-02: version 1.1.0, changelog section
- 34f1755 rel-02: docs clone main, drop the -b v1 note
- 4471cc1 rel-02: release tests check marketplace version and no -b v1 clone in docs
Verify: Verify passed: uv run --with pytest pytest -q tests/test_release.py && uv run --with pytest pytest -q && claude plugin validate .
Independent review: no gaps
