# fleet-06: A dispatched session that lands its goal ends its own tmux session
Status: approved
Goal: fleet-cleanup
Node: any
Deliverable: code
Land: goal
Verify: uv run --with pytest pytest -q tests/test_session_end.py tests/test_dispatch.py && uv run --with pytest pytest -q && claude plugin validate .
Hardware: none

## Goal
After a dispatched session sends `done <g> PR <url>`, it runs `friday session-end --goal <g>`, which
closes its own tmux session `friday-<g>` a few seconds later, so no idle Claude is left on the
node. A session that sent `blocked …` keeps running so the user can attach or use Remote Control.
tests/test_session_end.py proves when it acts and when it refuses, with a fake `tmux`.

## Steps
1. Add `friday session-end --goal <g>` (bin/friday): act only when `FRIDAY_DISPATCHED_FROM` is set,
   the current tmux session (`tmux display-message -p '#S'`) is `friday-<g>`, and the goal file in
   the current worktree says `Status: done`; then start a detached
   `setsid sh -c 'sleep 10; tmux kill-session -t =friday-<g>'` and print what it scheduled.
   Otherwise refuse with one line and exit non-zero, changing nothing.
2. Change the report text built by `report_text` (lib/friday_fleet.py): after sending the done
   message, run `friday session-end --goal <g>` and stop; after a blocked message, do not run it
   and stay open. Update the verbatim launch-line test in tests/test_dispatch.py.
3. Add `tests/test_session_end.py`: acts with all three conditions (fake `tmux` and `setsid`
   record the scheduled command); refuses when not dispatched, in a different tmux session, or
   when the goal is not done; never targets a session other than `friday-<g>`.
4. docs/fleet.md: what happens to sessions after done and after blocked, and how to close a
   blocked one by hand. CHANGELOG entry.

## Out of scope
- Worktrees, branches and trust entries (fleet-07).
- Restarting or resuming a blocked session.

## Log
