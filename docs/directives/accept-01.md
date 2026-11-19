# accept-01: `friday accept` refuses while tracked files are uncommitted, and says how to commit them
Status: done
Goal: attention
Node: any
Deliverable: code
Land: goal
Verify: uv run --with pytest pytest -q tests/test_accept_clean.py && uv run --with pytest pytest -q && claude plugin validate .
Hardware: none

## Goal
Work the user does during a review (routing a board, fixing a figure) is part of the directive
and must be committed before acceptance. `friday accept <id>` and `friday accept <id> --reject`
exit non-zero and change nothing while any tracked file is modified or staged, list those files,
and print the exact command to commit them as the directive's work. tests/test_accept_clean.py
proves it.

## Steps
1. bin/friday `cmd_accept`: before any write, run `git status --porcelain --untracked-files=no`;
   if anything is listed, print the paths, then
   `git commit -am "<id>: review changes" -m "Directive: <id>"` and the accept command to run
   after it, and exit 8 (new code; add it to the help text and the spec's exit-code table).
   Untracked files do not count.
2. Docs: docs/spec.md (accept and exit 8), docs/getting-started.md's review section and
   docs/recipes/pcb.md each say accept checks this; skills/directive/SKILL.md the same in one line.
3. tests/test_accept_clean.py: a modified tracked file makes accept and `--reject` exit 8, list the
   file and leave the directive unchanged; a staged change likewise; untracked files do not block;
   after the printed commit, accept succeeds, and `friday commits <id>` lists the review commit.
   CHANGELOG under Unreleased/Changed.

## Out of scope
- Committing the user's changes automatically (`--with-changes`).

## Log

### 2026-11-18
Commits:
- 7d97550 accept-01: friday accept exits 8 while tracked files are uncommitted
- f906925 accept-01: document that accept refuses with exit 8 while tracked files are uncommitted
- 7505da9 accept-01: test that accept refuses on uncommitted tracked files; changelog
Verify: Verify passed: uv run --with pytest pytest -q tests/test_accept_clean.py && uv run --with pytest pytest -q && claude plugin validate .
Independent review: no gaps
