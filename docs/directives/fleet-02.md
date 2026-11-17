# fleet-02: `friday dispatch --goal <g>` runs a goal on another node and reports back
Status: done
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

### 2026-11-17
Commits:
- b9d4375 dispatch: --dry-run prints the prepare script; launch line expands a leading ~ in plugin_dir
- a8de2ff execute: prepare notes the dispatch in runs/<id>/notes.md when FRIDAY_DISPATCHED_FROM is set
- 0cbd23a dispatch: run prepare and launch over ssh, record the dispatch in dispatches.jsonl on the master
- a2d0147 dispatch: launch line built by one function (tmux, claude flags, run and report text), --report-to refusal
- 7c6ce98 dispatch: one remote prepare script (trust, session, plugin checkout, clone reuse, goal worktree)
- a82ec47 dispatch: preconditions on the master with their own exit codes, node routing across a goal's directives
Verify: Verify passed: uv run --with pytest pytest -q tests/test_dispatch.py && uv run --with pytest pytest -q && claude plugin validate .
Independent review: gaps fixed in second review: 1. /home/david/Documents/claude_temp/friday/bin/friday:695-699 (cmd_dispatch, --dry-run branch): Step 1 says '--dry-run' prints the remote script and the launch line. The dry-run branch prints only the launch line and then returns. prepare_script is only built on the non-dry-run path (line 701), so the remote prepare script never appears in dry-run output. (evidence: 'if a.dry_run: print(f'launch: {launch}'); print('dry run: nothing changed on any node'); return 0'. test_dry_run_prints_launch_and_no_report_to only checks the launch text, so this goes untested.) 2. /home/david/Documents/claude_temp/friday/lib/friday_fleet.py:369 (launch_line): plugin_dir is passed through shlex.quote unchanged. The registry's documented form is a leading '~' (nodes.example.toml: plugin_dir = '~/friday'). shlex.quote('~/friday') gives '~/friday', so the remote bash never expands the tilde and claude gets a literal '~/friday' as --plugin-dir. On a node set up as the example shows, the worker session would start without the checked-out friday plugin, and /friday:execute would not be available. prepare_script handles this through remote_path() and cmd_dispatch swaps in the absolute worktree path, but plugin_dir gets neither treatment. (evidence: 'python3 -c 'import shlex;print(shlex.quote('~/friday'))'' prints ''~/friday''. launch_line has ''--plugin-dir', q(node.plugin_dir)'. The verbatim test uses an absolute plugin_dir ('/opt/my friday'), so it misses this case.)
