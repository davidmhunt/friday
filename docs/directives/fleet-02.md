# fleet-02: `friday dispatch <id>` starts a directive on another node and reports back
Status: approved
Goal: fleet
Node: any
Deliverable: code
Land: goal
Verify: uv run --with pytest pytest -q tests/test_dispatch.py && uv run --with pytest pytest -q && claude plugin validate .
Hardware: none

## Goal
From the master, `friday dispatch <id>` picks the node for an approved directive (fleet-01
routing), prepares a worktree there and starts a fresh Claude session running
`/friday:execute <id>`, with no manual step on the node. When the run finishes or blocks, the
worker session messages the master. tests/test_dispatch.py proves the refusals and the exact
commands built, against a fake `ssh`.

## Steps
1. Preconditions on the master, each a refusal with its own exit code and a one-line fix: the
   directive is `approved`; it is committed and the same on `origin/<base>` (base = current branch,
   or `--base`); the friday plugin's own HEAD is on its origin (the node checks out that commit);
   the chosen node is reachable (`ssh -o ConnectTimeout=5 -o BatchMode=yes`). `--node <name>`
   overrides routing. `--dry-run` prints the remote script and launch line and changes nothing.
2. One remote prepare script per dispatch (via `friday_fleet.ssh_cmd`): refuse if `repos` (or a
   parent) is untrusted in `~/.claude.json`, or if a tmux session `<id>` already exists; fetch
   `plugin_dir` and check out the master's plugin commit, detached; use the clone at
   `<repos>/<repo-name>` if it exists and its origin matches the master's (refuse on a mismatch,
   naming both URLs), else clone it there from the master's origin URL; fetch. The existing
   checkout's working tree and branch are never touched; create the worktree
   `<repos>/<repo-name>.friday/<id>` on a new branch `friday/<id>` from `origin/<base>` (refuse if
   that branch already exists on the node). For the running count used by routing, a script lists
   the node's tmux sessions whose names are directive ids.
3. Launch line (built by one function, unit-tested verbatim):
   `tmux new -d -s <id> -c <worktree> env FRIDAY_RUNTIME=<runtime> FRIDAY_DISPATCHED_FROM=<master-host> claude --model opus --permission-mode auto --remote-control --name <id>.<node> --plugin-dir <plugin_dir> --append-system-prompt <report text> "/friday:execute <id>"`.
   The session name uses `.`, not `@` (SendMessage rejects names containing `@`). `<report text>`
   tells the session: when the friday:execute workflow returns, send session `<report_to>` (from
   `--report-to`, else the registry's `report_to`; refuse if neither is set) exactly one message
   with SendMessage: `done <id> PR <url>` or `blocked <id>: <reason>`, then stop. All values are
   shell-quoted with `shlex.quote`.
4. Record the dispatch on the master only: append one JSON line (id, repo, node, tmux session,
   worktree, base, plugin commit, report_to, time) to `~/.local/state/friday/dispatches.jsonl`
   (honour `XDG_STATE_HOME`). The master does not edit the directive file.
5. In `workflows/execute.js` Prepare: if `FRIDAY_DISPATCHED_FROM` is set, the prepare agent adds a
   dated Log line "Dispatched from <host> to <this host>" to the directive in the same commit as
   `friday start`.
6. Add `tests/test_dispatch.py` with a fake `ssh` on `$FRIDAY_SSH` and a local bare repo as
   origin: each refusal (not approved, not pushed, plugin not pushed, unreachable, untrusted, tmux
   session exists, no report_to); `--dry-run` output; the exact launch line; the dispatches.jsonl
   record; reuse of an existing clone and refusal on an origin mismatch; `--node` override; that `any` picks the node with fewer running sessions.

## Out of scope
- herdr launcher; cloud sessions; dispatch to targets (they have no Claude).
- Updating Claude Code on nodes; setting trust (dispatch only checks it).
- Watching or restarting dispatched sessions; cross-node `friday status` (phase 4).
- The live laptop -> Alfred run: that is the phase gate after this lands (see fleet-03).

## Log
