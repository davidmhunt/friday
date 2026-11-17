# fleet-08: `friday dispatch --goal <g> --resume` restarts a stopped goal in its existing worktree
Status: approved
Goal: fleet-cleanup
Node: any
Deliverable: code
Land: goal
Verify: uv run --with pytest pytest -q tests/test_dispatch_resume.py tests/test_dispatch.py && uv run --with pytest pytest -q && claude plugin validate .
Hardware: none

## Goal
A dispatched goal that stopped (blocked, a refused command, a crashed session) restarts with
`friday dispatch --goal <g> --resume`: on the node that holds its worktree, an idle or missing
`friday-<g>` session is replaced by a fresh one in the same worktree, which reloads project
settings and runs the goal's remaining directives. Work in progress is kept. A busy session, a
missing worktree or a goal already done refuses. tests/test_dispatch_resume.py proves each case.

## Steps
1. `--resume`: find the node from the latest `dispatches.jsonl` record for the goal (or `--node`);
   over `friday_fleet.ssh_cmd` check that the worktree `<repos>/<repo>.friday/<g>` exists on branch
   `friday/<g>` and report its uncommitted files (kept, not touched). Refuse when the worktree is
   missing (use a normal dispatch), when the goal file there says `done`, or when the
   `friday-<g>` session exists and its pane is not idle at a prompt (reuse status-01's waiting
   rule if present, else the prompt patterns in `friday_fleet`).
2. Remaining directives: read the goal file in the node's worktree (not the master's) and list
   directives not `done`; a `blocked: …` directive is listed with its reason and resumes only with
   `--unblock <id>`, which resets its Status to `approved` in the worktree as an uncommitted edit
   (the finish commit carries it).
3. Restart: `tmux kill-session -t =friday-<g>` when it exists, then the same launch line as dispatch
   (built by `launch_line`, with the remaining ids), and append a `resume` record to
   `dispatches.jsonl`. `--dry-run` prints the checks and the launch line only.
4. Add `tests/test_dispatch_resume.py` with a fake `ssh`/`tmux`: resume after a blocked land
   (directive done, branch unpushed) lists only later directives; refusals for busy session,
   missing worktree, goal done, blocked directive without `--unblock`; `--unblock` resets that
   status; uncommitted files are reported and untouched; the record and dry-run output.
5. docs/fleet.md: when to use `--resume` and `--unblock`. CHANGELOG entry.

## Out of scope
- Resuming on a different node than the worktree's; moving worktrees between nodes.
- Restarting automatically without the user or the master session asking.

## Log
