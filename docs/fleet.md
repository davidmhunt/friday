# Fleet: running a goal on another machine

A goal can run on a node other than the one you plan on. `friday dispatch --goal <g>` prepares a
worktree on that node, starts a Claude session in tmux there, and the session messages your master
session when the goal lands or a directive blocks. This page is everything you need to add a node and
dispatch to it.

## Roles

- **master**: the machine you work on; it runs the planning session and receives reports.
- **worker**: a machine that runs directives (`Node: any`, `tag:<x>`, `host:<name>`).
- **target**: a device driven over SSH by whichever node runs the directive (a rover, a Pi). It never
  runs directives; it is only checked for reachability.

## Slash commands

From any session that loads the plugin (including over Remote Control), these run the CLI for you:

| Slash command | CLI form |
|---|---|
| `/friday:status` | `friday status` |
| `/friday:nodes [--check]` | `friday nodes` (lists the registry; with `--check` it probes each node over ssh) |
| `/friday:dispatch <goal>` | `friday dispatch --goal <goal>`: runs `--dry-run` first, shows it, runs for real after you say yes |
| `/friday:clean <node>` | `friday nodes --clean <node>`: runs `--dry-run` first, shows it, runs for real after you say yes |

## The registry (`nodes.toml`)

`friday` reads the first file that exists, in this order:

1. `$FRIDAY_NODES`
2. `nodes.toml` in the friday folder (the plugin clone; gitignored, because it holds real tailnet names)
3. `~/.config/friday/nodes.toml`

Copy `nodes.example.toml` to one of those places and edit it. `friday nodes` prints the file in use and
the nodes it holds.

An installed (cached) copy of the plugin does not see the clone's `nodes.toml`: its friday folder is
the cache, not your clone. Either start Claude with `--plugin-dir <your friday clone>` or set
`FRIDAY_NODES` (or use `~/.config/friday/nodes.toml`, which every copy finds).

### Format

```toml
# Name of the master's Claude session that workers message (optional; --report-to overrides it).
report_to = "friday-master"

[node.laptop]
role = "master"
ssh = "david@laptop-ts"
repos = "~/Documents"
plugin_dir = "~/friday"
tags = ["laptop"]

[node.alfred]
role = "worker"
ssh = "david@alfred-ts"
runtime = "container"
tags = ["gpu"]
repos = "~/Documents"
plugin_dir = "~/friday"

[node.ground-bot]
role = "target"            # a target needs only role and ssh (and optional tags)
ssh = "pi@ground-bot-ts"
tags = ["rover"]
```

Keys of `report_to` and `[dash]` (top level) and of each `[node.<name>]` table:

| key | meaning |
|---|---|
| `report_to` | name of the master's session that workers message; optional |
| `role` | `master`, `worker` or `target`; required |
| `ssh` | `user@host` or an ssh config alias; required and unique per node |
| `runtime` | `native` (default) or `container`; passed to the worker as `FRIDAY_RUNTIME` |
| `tags` | list of labels that `Node: tag:<x>` routes on |
| `repos` | directory holding the node's repos (`~` allowed); required for master and worker |
| `plugin_dir` | where the friday plugin is cloned on the node; required for master and worker |
| `launcher` | how directives start; only `tmux` is supported (the default) |
| `[dash]` `port` | port `friday dash` listens on (top-level `[dash]` table); default 8787 |

## Routing

A directive's `Node:` line picks the node:

- `any`: the worker with the fewest running `friday-*` tmux sessions (ties go to registry order).
- `tag:<x>`: a worker or master carrying the tag, lowest load first. If only a target has the tag, the
  master runs the directive and drives the target over SSH.
- `host:<name>`: that node, named explicitly. A target cannot be named; use a `tag:` line instead.

A goal runs as one session on one node, so `dispatch` takes the nodes that satisfy every remaining
directive's `Node:` line and picks the least loaded. If no node satisfies them all, it refuses; make the
lines agree or pass `--node <name>`.

## Where work happens on a node

Each node has `repos`. For a goal `<g>` in repo `<repo>`:

- An existing clone at `<repos>/<repo>` is reused (its origin must match the master's origin); if there
  is none, it is cloned from the master's origin.
- The goal gets a worktree at `<repos>/<repo>.friday/<g>` on branch `friday/<g>`. The branch starts from
  `origin/friday/<g>` when that exists, otherwise from the goal's Base (`origin/<Base>`).
- Your checkout on the node is never touched: no checkout, reset or stash happens in it.

To change where work happens, change `repos` for that node. It must be trusted by `claude` (see below).

Every remote command starts with `export PATH="$HOME/.local/bin:$PATH"`. Non-interactive ssh does not
read `.zshrc`, and `claude` and `uv` usually live in `~/.local/bin`, so without it they are not found.

## One-time node setup

On each worker (and on the master, which is also a node):

1. Tailscale with Tailscale SSH on, so `ssh <user@host>` works from the master without a prompt
   (dispatch uses `BatchMode=yes`). Alfred's is `david@alfred-ts`.
2. `claude` installed, signed in, and current (`claude update`).
3. `gh auth login`, so the goal's PR can be opened.
4. `tmux` installed.
5. The friday clone at `plugin_dir` (`git clone <friday origin> ~/friday`). Dispatch checks out the
   master's plugin commit there.
6. `friday` on PATH: `python3 ~/friday/bin/friday install` once on the node (or let
   `friday nodes --setup <node>` do it). After that just `friday`; remove it with
   `ssh <node> friday uninstall`. The `uv run` and `python3` forms still work.
7. Trust `repos` once: run `claude` in that directory on the node and accept the trust prompt.
   Dispatch refuses (`untrusted`) until `repos` or a parent is trusted in `~/.claude.json`.

Then check from the master:

```
friday nodes --check
```

It probes each node over ssh and reports which are reachable and how many `friday-*` sessions run.
For each master and worker it also reports two Claude Code first-run prompts that would stop a
dispatched session, because nobody is there to answer them:

- `workflow prompt`: the workflow usage warning; cleared by `skipWorkflowUsageWarning: true`.
- `auto-mode prompt`: the auto-mode opt-in; cleared by `skipAutoPermissionPrompt: true`.

Each is a FAIL with the fix `friday nodes --setup <node>`. A missing or unparsable
`~/.claude/settings.json` counts as both prompts.

### `friday nodes --setup <node>`

```
friday nodes --setup alfred [--yes]
```

Prints the exact keys and the file (`~/.claude/settings.json` on that node), then asks `y/N` on the
terminal. Without a TTY it refuses unless you pass `--yes`. On confirmation it merges only those two keys
into the file: other keys stay as they are, the file is written to a temp file and renamed, and the
previous one is kept once as `settings.json.friday-bak`. It never touches trust, credentials or
permission rules. Run `friday nodes --check` again afterwards.

### Setting up the master (learned on the laptop)

The master is a node too, and dispatch reaches it by ssh like any other:

- It needs an ssh server, or `tailscale set --ssh` so Tailscale SSH answers for it.
- `ssh` in the registry is the node's tailnet name (for example `david@laptop-ts`), not its local hostname.
- Accept the host key once: run `ssh <user@host>` by hand and answer `yes`. `BatchMode` cannot answer it.
- Use key auth so `BatchMode=yes` works: `ssh-copy-id <user@host>` (not needed with Tailscale SSH).

## Dispatching

Approve the goal and its first remaining directive, commit the goal and directive files, and publish
them to `origin` (`friday/<g>` if it exists there, else the Base). Run `friday dispatch` from the repo you want dispatched: the goal and its origin come from the
current checkout. Then:

```
friday dispatch --goal <g> [--node <name>] [--report-to <session>] [--dry-run]
```

`--dry-run` prints the prepare script and launch line and changes nothing on any node. A real run
prepares the worktree over ssh, starts tmux session `friday-<g>` there running `claude` with Remote
Control, and tells it to run the goal's remaining directives in order and land the goal.

### Ending a finished session

`friday session-end --goal <g>` closes the dispatched session's own tmux session `friday-<g>` ten
seconds later. It acts only when `FRIDAY_DISPATCHED_FROM` is set, the current tmux session is
`friday-<g>`, and the goal file says `Status: done`; otherwise it prints one line and exits 1.

After the session sends `done <g> PR <url>` it runs `friday session-end --goal <g>` and stops, so no
idle Claude is left on the node. After `blocked ...` it does not run it and stays open, so you can
attach (`tmux attach -t friday-<g>`) or use Remote Control to unblock it.

To close a blocked session by hand, on the node: `tmux kill-session -t =friday-<g>`. The worktree
and branch stay as they are.

### Restarting a stopped goal (`--resume`)

Use `--resume` when a dispatched goal stopped and its worktree is still on the node: the session
reported `blocked`, a command was refused, or the session crashed or was closed. A normal dispatch
refuses then (exit 33, the worktree exists).

```
friday dispatch --goal <g> --resume [--unblock <id>]... [--node <name>] [--report-to <session>] [--dry-run]
```

The node is the one in the latest `dispatches.jsonl` record for the goal; `--node` is needed only
when there is no record. Moving a goal to another node is not supported. Resume checks the worktree
`<repos>/<repo>.friday/<g>` is on branch `friday/<g>`, reports its uncommitted files (kept, never
touched), and lists the directives that are not `done`, read from the goal file in the worktree.
It then kills an idle or leftover `friday-<g>` session, starts a fresh one in the same worktree
(which reloads project settings) with the dispatch launch line and the remaining directive ids, and
appends a `resume` record to `dispatches.jsonl`. `--dry-run` prints the checks and the launch line
and changes nothing, including `--unblock`.

A directive marked `blocked: <reason>` is listed with its reason and is not resumed on its own.
Fix the cause, then pass `--unblock <id>`: it resets that directive's Status to `approved` in the
worktree as an uncommitted edit, and the directive's `friday finish` commit carries it.

| kind | exit | cause |
|---|---|---|
| no-record | 21 | no dispatch record for the goal and no `--node` |
| no-worktree | 22 | the worktree is missing, or is not on `friday/<g>` (use a normal dispatch) |
| goal-done | 23 | the goal is done, or no directive is left to run |
| busy | 24 | session `friday-<g>` exists and is not idle at a prompt |
| blocked | 25 | a remaining directive is blocked and not named by `--unblock` |
| unblock | 26 | `--unblock` names a directive that is not in the goal, or the reset failed |

Resume runs only when you or the master session ask for it; nothing restarts a goal automatically.

### Refusals

Each refusal prints one line and a fix on stderr and exits with its own code.

| kind | exit | cause |
|---|---|---|
| goal | 10 | no such goal, or its Status is not approved or running |
| format | 11 | `friday check --goal <g>` reports errors |
| directives | 12 | a directive file is missing, nothing remains, or the first remaining one is not approved |
| land-pr | 13 | a remaining directive has `Land: pr`; run those locally with `/friday:execute` |
| unpushed | 14 | no origin, or the goal or directive files are uncommitted or differ from the source ref on origin |
| plugin | 15 | the friday folder is not a git clone, or its HEAD is not on its origin |
| registry | 16 | no nodes file, or it is invalid |
| route | 17 | no node satisfies every remaining directive's `Node:` line |
| node | 18 | `--node` names a missing node or a target |
| unreachable | 19 | the chosen node did not answer over ssh |
| report-to | 20 | no `--report-to` and no `report_to` in the registry |
| settings | 27 | the source ref's `.claude/settings.json` lacks a friday allow rule; run `friday init`, commit and push |

The node itself can also refuse (the dispatch command exits with the node's code):

| kind | exit | cause |
|---|---|---|
| untrusted | 30 | `repos` is not trusted in `~/.claude.json` |
| session | 31 | tmux session `friday-<g>` already exists |
| origin | 32 | the clone's origin is missing or differs from the master's |
| worktree | 33 | the worktree path already exists |
| branch | 34 | local branch `friday/<g>` already exists in the clone |
| plugin | 35 | cannot check out the plugin commit at `plugin_dir` |
| git | 36 | clone, fetch or worktree add failed |

## Cleaning up finished goals

Worktrees, branches and trust entries pile up on a node. Clean them with:

```
friday nodes --clean <node> [--dry-run]
```

`--dry-run` prints the plan and changes nothing. `friday dispatch` runs the same clean for the target
node first, without a prompt, and prints what it removed. If the clean fails, dispatch says so and
carries on.

The clean looks at each worktree `<repos>/<repo>.friday/<goal>` on the node. The master decides:

- **Finished**: a merged PR exists for `friday/<goal>` (`gh pr list --state merged --head
  friday/<goal>`; squash merges are found this way, not by ancestry), or `friday/<goal>` is gone from
  origin and the goal file in the worktree says `Status: done`. Without `gh` on the master only the
  branch-gone rule is used, and the clean says so.
- **Kept, with a one-line reason**: unfinished goals, dirty worktrees (tracked or untracked changes,
  ignoring `runs/`), and goals whose `friday-<goal>` tmux session is not at an idle prompt.

For each finished goal the node removes the tmux session (only if idle), the worktree (never forced),
the local branch `friday/<goal>`, and the goal's entry under `projects` in `~/.claude.json` (other keys
stay).

Not cleaned: remote branches (turn on GitHub's "delete branch on merge"), clones, and the master's own
checkout. A clone whose folder name differs from its origin repo name is a stray clone: the clean
reports it and never deletes it, so remove stray clones by hand.

## The master and reports

The worker reports with one message to the master's session, so the master must run with Remote Control
on and a session name without `@` (for example `claude --remote-control --name friday-master`). Put that
name in `report_to` or pass `--report-to`. The message is `done <g> PR <url>` or `blocked <g> <id>: <reason>`.

## Where dispatches are recorded

Each dispatch appends one JSON line to `dispatches.jsonl` on the master, at
`$XDG_STATE_HOME/friday/dispatches.jsonl` (default `~/.local/state/friday/dispatches.jsonl`): goal,
directives, node, tmux session, worktree, branch, source ref, plugin commit, report target, time. Goal
and directive files are not changed by dispatching. On the node, `runs/<id>/notes.md` notes where the
dispatch came from.

## Hardware

Hardware leases live on the machine that runs the SSH command (`~/.local/state/friday/leases/`), so a
lease on one node says nothing about another. Keep one master per target: two masters driving the same
device do not see each other's leases.

## When no message arrives

Attach to the worker's session on the node: `ssh <node> -t tmux attach -t friday-<g>` (or
`tmux attach -t friday-<g>` if you are on it). Or open the session in the Claude app: the worker runs
with Remote Control and is named `<g>.<node>`. If the session is gone, check the goal's branch
`friday/<g>` on origin and the worktree on the node.
