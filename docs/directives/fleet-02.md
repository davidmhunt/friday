# fleet-02: `friday dispatch --goal <g>` runs a goal on another node and reports back
Status: approved
Goal: fleet
Node: any
Deliverable: code
Land: goal
Verify: uv run --with pytest pytest -q tests/test_dispatch.py && uv run --with pytest pytest -q && claude plugin validate .
Hardware: none

## Goal
From the master, `friday dispatch --goal <g>` picks one node for an approved goal (fleet-01
routing), prepares a worktree there on the goal branch `friday/<g>` and starts a fresh Claude
session that runs the goal's remaining directives in order with `/friday:execute`, with no manual
step on the node. The goal lands as its one PR from that node (`friday land --goal`, as execute
already does after the last directive). When the goal is done or a directive blocks, the worker
session messages the master. tests/test_dispatch.py proves the refusals and the exact commands
built, against a fake `ssh`.

## Steps
1. Preconditions on the master, each a refusal with its own exit code and a one-line fix: the goal
   is `approved` or `running` and `friday check --goal <g>` has no errors; its remaining directives
   (those not `done`, in listed order) exist, the first is `approved`, and none has `Land: pr`
   (those run locally on their own branch); the goal and directive files are committed and the
   same on the goal's source ref, which is `origin/friday/<g>` when that branch exists on origin,
   else `origin/<Base>`; the friday plugin's own HEAD is on its origin (the node checks out that
   commit); the chosen node is reachable (`ssh -o ConnectTimeout=5 -o BatchMode=yes`). Routing
   takes the remaining directives' `Node:` lines together: the node must satisfy every one (refuse
   naming the directives that conflict). `--node <name>` overrides routing. `--dry-run` prints the
   remote script and launch line and changes nothing.
2. One remote prepare script per dispatch (via `friday_fleet.ssh_cmd`): refuse if `repos` (or a
   parent) is untrusted in `~/.claude.json`, or if a tmux session `friday-<g>` already exists;
   fetch `plugin_dir` and check out the master's plugin commit, detached; use the clone at
   `<repos>/<repo-name>` if it exists and its origin matches the master's (refuse on a mismatch,
   naming both URLs), else clone it there from the master's origin URL; fetch. The existing
   checkout's working tree and branch are never touched. Create the worktree
   `<repos>/<repo-name>.friday/<g>` on branch `friday/<g>`: tracking `origin/friday/<g>` when it
   exists, else a new branch from `origin/<Base>` with `--no-track` (as `friday start` does).
   Refuse if the worktree path or a local `friday/<g>` branch already exists on the node. For the
   running count used by routing, a script counts the node's tmux sessions named `friday-*`.
3. Launch line (built by one function, unit-tested verbatim):
   `tmux new -d -s friday-<g> -c <worktree> env FRIDAY_RUNTIME=<runtime> FRIDAY_DISPATCHED_FROM=<master-host> claude --model opus --permission-mode auto --remote-control --name <g>.<node> --plugin-dir <plugin_dir> --append-system-prompt <report text> <run text>`.
   The session name uses `.`, not `@` (SendMessage rejects names containing `@`). `<run text>`
   lists the remaining directive ids and tells the session to run `/friday:execute <id>` for each
   in that order, starting the next only when the previous ended done, and to stop at the first
   that blocks. `<report text>` tells it to then send session `<report_to>` (from `--report-to`,
   else the registry's `report_to`; refuse if neither is set) exactly one message with
   SendMessage: `done <g> PR <url>` (the URL from the goal landing) or
   `blocked <g> <id>: <reason>`, then stop. All values are shell-quoted with `shlex.quote`.
4. Record the dispatch on the master only: append one JSON line (goal, directive ids, repo, node,
   tmux session, worktree, branch, source ref, plugin commit, report_to, time) to
   `~/.local/state/friday/dispatches.jsonl` (honour `XDG_STATE_HOME`). The master edits no goal
   or directive file.
5. In `workflows/execute.js` Prepare: if `FRIDAY_DISPATCHED_FROM` is set, the prepare agent appends
   one dated line "Dispatched from <host> to <this host>" to `runs/<id>/notes.md` (untracked), so
   `friday finish` carries it into the directive's Log `Notes:`. Prepare still commits nothing.
6. Add `tests/test_dispatch.py` with a fake `ssh` on `$FRIDAY_SSH` and a local bare repo as
   origin: each refusal (goal not approved, goal has format errors, first remaining directive not
   approved, a remaining directive with `Land: pr`, files not pushed, plugin not pushed,
   unreachable, conflicting `Node:` lines, untrusted, tmux session exists, worktree or local goal
   branch exists, no report_to); `--dry-run` output; the exact launch line including the
   directive order; the worktree from `origin/friday/<g>` when it exists and from `origin/<Base>`
   when it doesn't; the dispatches.jsonl record; reuse of an existing clone and refusal on an
   origin mismatch; `--node` override; that `any` picks the node with fewer `friday-*` sessions;
   the dispatched-from line in notes.md.

## Out of scope
- Dispatching a single directive, or goals with `Land: pr` directives; parallel directives within
  a goal.
- herdr launcher; cloud sessions; dispatch to targets (they have no Claude).
- Updating Claude Code on nodes; setting trust (dispatch only checks it).
- Watching or restarting dispatched sessions; cross-node `friday status` (phase 4).
- The live laptop -> Alfred run: that is the phase gate after this lands (see fleet-03).

## Log
- 2026-11-17: amended to the goal model before running (HANDOFF sections 5 and 7), approved by the
  user: dispatch takes a goal and works on `friday/<goal>` instead of a per-directive branch
  `friday/<id>`; the dispatched-from note goes to `runs/<id>/notes.md` since `friday start` no
  longer commits.
