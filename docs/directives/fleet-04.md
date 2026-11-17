# fleet-04: Dispatch trusts the new worktree and names it from origin
Status: approved
Goal: fleet-hardening
Node: any
Deliverable: code
Land: goal
Verify: uv run --with pytest pytest -q tests/test_dispatch.py && uv run --with pytest pytest -q && claude plugin validate .
Hardware: none

## Goal
The prepare script leaves the new goal worktree trusted in the node's `~/.claude.json`, so the
dispatched session starts without the "trust this folder" dialog, and the clone and worktree are
named after the master's origin repo, not the folder dispatch was run from.
tests/test_dispatch.py proves both against a fake `ssh`.

## Steps
1. In the prepare script (`lib/friday_fleet.py`), after the worktree exists and only when the
   existing trust check passed (`repos` or a parent trusted): set
   `projects[<worktree realpath>].hasTrustDialogAccepted = true` in `~/.claude.json`, keeping every
   other key; write to a temp file in the same directory and `os.replace` it; back up the original
   once to `~/.claude.json.friday-bak` if no backup exists. If the file is missing or unreadable,
   refuse `untrusted` as today. Print `FRIDAY_TRUSTED <path>`.
2. Repo name: derive `<repo-name>` from the master's origin URL (last path segment without
   `.git`), not the local toplevel folder name, in `cmd_dispatch` and the dispatches.jsonl record,
   so running from `../friday-plugin` still gives `<repos>/friday` and `<repos>/friday.friday/<g>`.
3. Extend `tests/test_dispatch.py`: the worktree entry is added with other projects and keys
   unchanged, and the backup is written once; no write when `repos` is untrusted (refusal as
   before); the repo name comes from origin when the master's folder name differs (for example a
   worktree named `friday-plugin`); dry-run output shows the trust step.

## Out of scope
- Trusting `repos` itself (still a one-time manual step per node, done by running `claude` there).
- Workflow approval and auto-mode opt-in prompts (fleet-05).
- Cleaning up worktrees, branches or trust entries after a goal lands.

## Log
