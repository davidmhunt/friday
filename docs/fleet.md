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
| `/friday:nodes --waiting` | `friday nodes --waiting`: one line per session waiting on a prompt (node, goal, directive, age, message); exit 0 none, 10 some, 2 a node unreachable |
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
| `tailnet` | tailnet device name, only when it differs from the host in `ssh`; the dash matches pushes and builds the master's URL with it; optional |
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

Plan amendments to a dispatched goal are commits on its goal branch (checked with `friday check`,
pushed; run `friday approve --goal <g>` again when `## Allowed commands` changed); the node
picks them up at its next fetch. An amendment to the running directive takes effect when it restarts.

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
6. `uv` installed (https://docs.astral.sh/uv/getting-started/installation/). friday runs on a uv-managed
   Python 3.12, so the node's system Python (3.10 on Ubuntu 22.04) is not used.
7. `friday` on PATH: `python3 ~/friday/bin/friday install` once on the node (or let
   `friday nodes --setup <node>` do it). It installs Python 3.12 into friday's private directory (`~/.local/share/friday/python`, not on PATH), records the interpreter in
   `~/.local/state/friday/python` and writes a `~/.local/bin/friday` shim. After that just `friday`; remove
   it with `ssh <node> friday uninstall`.
8. Trust `repos` once: run `claude` in that directory on the node and accept the trust prompt.
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

For each node it reports `uv`, the recorded friday Python and its version, with the fixes
`friday install` when none is recorded, it does not run, or it is older than 3.11.

It also probes three worker prerequisites, each reported with a fix line when missing: `uv` (on PATH or
`~/.local/bin`; install from https://docs.astral.sh/uv/getting-started/installation/), `gh auth status`
(push credentials for `friday land`; run `gh auth login` on the node) and `claude auth status` (signed
in; run `claude` and `/login` on the node). Sign-in and `gh auth login` are for a person to do: friday
reports them and never does them.

### `friday nodes --setup <node>`

```
friday nodes --setup alfred [--yes]
```

First prints `prerequisites:` with one line per item (`uv`, `gh auth`, `claude signed in`: ok, or
missing with its fix), the same probe `--check` runs. A missing item does not stop the settings step.
For a node whose role is `target`, `--setup` changes nothing on the node: it prints the prerequisites and
the `nodes.toml` edit that makes it a worker (`role = "worker"`, `repos`, `plugin_dir`) and exits 1; edit
the registry and re-run it.

Then prints the exact keys and the file (`~/.claude/settings.json` on that node), then asks `y/N` on the
terminal. Without a TTY it refuses unless you pass `--yes`. On confirmation it merges only those two keys
into the file: other keys stay as they are, the file is written to a temp file and renamed, and the
previous one is kept once as `settings.json.friday-bak`. It never touches trust, credentials or
permission rules. Run `friday nodes --check` again afterwards.

### The node identity file (`node.toml`)

After the settings step, `--setup` also writes `~/.config/friday/node.toml` on the node (temp file and
rename; it is listed in the same y/N summary). It holds three keys, and unknown keys are an error:

```toml
name = "alfred"                       # the node's registry name
repos = "~/repos"                     # the node's repos directory
dash = "http://master-ts:8787"        # the dash URL: master tailnet or ssh host, [dash] port
```

A node has no `nodes.toml`, so `friday status` and `friday status --push` read this file: the
snapshot's `node` is `name` (not the hostname), `repos` is what gets scanned, and `dash` is the push
URL. Order for the name: `--node`, a matching registry entry, `node.toml`, hostname. Push URL: `--to`,
the registry master, `node.toml`. A malformed file is reported in the snapshot's `errors` and status
still prints. `$FRIDAY_NODE_FILE` overrides the path. A setup on the master writes one too; its
registry still wins.

### Allow rules live in the repo

A plugin cannot grant permissions, so friday's own commands are allowed by rules in each repo's
tracked `.claude/settings.json`. `friday init` merges them in (keeping other keys and rules, never
touching `settings.local.json`) and does not commit; the plan skill runs it before the plan commit.
A node clones the repo, so the rules reach it through git, and dispatch refuses (exit 27) a source
ref that lacks them.

### Setting up the master (learned on the laptop)

The master is a node too, and dispatch reaches it by ssh like any other:

- It needs an ssh server, or `tailscale set --ssh` so Tailscale SSH answers for it.
- `ssh` in the registry is the node's tailnet name (for example `david@laptop-ts`), not its local hostname.
- Accept the host key once: run `ssh <user@host>` by hand and answer `yes`. `BatchMode` cannot answer it.
- Use key auth so `BatchMode=yes` works: `ssh-copy-id <user@host>` (not needed with Tailscale SSH).

### Directives that need another repo

A dispatched session works in its goal worktree. When the user setting
`permissions.blockReadsOutsideWorkingDirectories` (or `permissions.blockFileToolReadsOutsideWorkingDirectories`)
is true on the node, a read outside the working directories prompts, and an unattended session waits.
`friday nodes --check` prints `outside-reads prompts` and a warning for such a node. A directive that
needs files from another repo handles it one of two ways: copy what it needs into the goal branch
(preferred, it is reviewable and travels with the branch), or the user allows the read on the node.
friday never changes that setting.

## Dispatching

Approve the goal and its first remaining directive, commit the goal and directive files on
`friday/<g>`, and push that branch to `origin`. Run `friday dispatch` from the repo you want dispatched: the goal and its origin come from the
current checkout. Then:

```
friday dispatch --goal <g> [--node <name>] [--report-to <session>] [--dry-run]
```

`--dry-run` prints the prepare script and launch line and changes nothing on any node. A real run
prepares the worktree over ssh, starts tmux session `friday-<g>` there running `claude` with Remote
Control, and tells it to run the goal's remaining directives in order and land the goal.

### Pre-approving commands for a dispatched run

A dispatched session has nobody at the prompt, so a command that would ask (a hardware command,
`friday nodes --clean`, `friday release`, a nested `friday dispatch`) leaves it waiting until you
attach or `--resume`. Pre-approve what the goal needs in each directive's `## Allowed commands`:

```markdown
## Allowed commands
- `ssh ground-bot ./run ros2 topic list`
- `friday nodes --clean alfred`
- `./run tools/bench.sh *`
```

One backticked command per bullet; `*` matches any text; only a single simple command (no `&&`, `;`,
`|`, backticks or `$(`). The list is read from the directive as committed on `origin/friday-plan/<goal>` (the
plan you approved), never from the goal branch, so run `friday approve --goal <g>` before
dispatching (it pushes that ref; agents cannot). Without it the commands prompt. To add a command
later, commit the amendment on the goal branch, run `friday check`, push the branch, run
`friday approve --goal <g>` again, and the node picks it up after a fetch (its next `friday start`
or after `--resume`). The deny list still wins: `sudo`, force-push and push to
main stay refused even if listed (a listed `git push` to a branch other than the goal branch is a
`friday check` error; a listed explicit tag push, destination `refs/tags/<name>`, runs), so `sudo` on a target over `ssh` stays a step you do. A
pre-approved hardware command still takes the lease. See [spec.md](spec.md) section 5.

### Ending a finished session

`friday session-end --goal <g>` closes the dispatched session's own tmux session `friday-<g>` ten
seconds later. It acts only when `FRIDAY_DISPATCHED_FROM` is set, the current tmux session is
`friday-<g>`, and the goal file says `Status: done`; otherwise it prints one line and exits 1.

After the session sends `done <g> PR <url>` it runs `friday session-end --goal <g>` and stops, so no
idle Claude is left on the node. After `blocked ...` it does not run it and stays open, so you can
attach (`tmux attach -t friday-<g>`) or use Remote Control to unblock it.

To close a blocked session by hand, on the node: `tmux kill-session -t '=friday-<g>'`. The worktree
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
Fix the cause, then pass `--unblock <id>`: it runs `friday unblock <id>` in the
worktree: the directive's Status goes back to `approved` with a Log line, in one commit (other
uncommitted files are left alone).

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

## Targets and workers

A directive can reach a device in two ways. Pick by what the work needs.

**A target directive** drives a device (a robot) over ssh from the node that runs it. Keep it thin. It
may run:

- named, reviewed project scripts, such as a read-only probe and one smoke test, each listed under
  `## Allowed commands` (`tools/probe.sh *`);
- single-purpose writes you approve one at a time (a tag, a file copy), at the prompt or as an exact
  command.

It does not pre-approve any remote command (`ssh <host> *`, a remote `bash -c *`) or a remote build or
install (`docker build`, `colcon build`, `make`, `cmake`, `cargo build`, `pip install`, `uv sync`,
`apt`). `friday check` warns on those patterns (not an error), and the plan skill routes such work to
a worker. Over a broad `ssh` pattern the target's whole shell is open to the session, with no review.

**A worker goal** (`Node: host:<robot>`) is for work that needs iteration on the robot: debugging,
building, editing its checkout, hardware tests. The robot's own session runs it under that machine's
local permission mode, so it has the robot's tools, its checkout and a shell on the machine. Use a
worker when the steps are "try, look, change, try again".

To promote a target to a worker, run `friday nodes --setup <robot>`: it lists the missing prerequisites
(`uv`, `gh auth`, `claude` sign-in) with their fixes and prints the `nodes.toml` change (`role =
"worker"`, `repos`, `plugin_dir`), exiting 1 until you make it. Edit the registry, re-run
`--setup`, then `friday nodes --check` (see
[`friday nodes --setup <node>`](#friday-nodes---setup-node)). Then give the directive
`Node: host:<robot>` and dispatch it like any goal.

### A read-only probe recipe

Keep the fixed list of read-only commands in a project script, so the directive pre-approves one name,
not a shell. `tools/probe.sh <robot>` runs them over one ssh call and prints a labelled section for
each:

```bash
#!/usr/bin/env bash
# tools/probe.sh <robot>: read-only state of a robot, one ssh call, labelled sections.
set -euo pipefail
robot="${1:?usage: tools/probe.sh <robot>}"
ssh "$robot" 'for c in "uname -a" "cat /etc/os-release" "uptime" "df -h /" "docker ps" \
    "ros2 node list" "ros2 topic list"; do
  printf "== %s ==\n" "$c"; sh -c "$c" 2>&1 || true
done'
```

Review the script like code: its command list is the whole permission. List it under
`## Allowed commands` as a single bullet:

```markdown
## Allowed commands
- `tools/probe.sh *`
```

The probe takes the robot's hardware lease when the robot matches a `hardware` pattern, like any
`ssh`. See [recipes/robot.md](recipes/robot.md).

## Hardware

Hardware leases live on the machine that runs the SSH command (`~/.local/state/friday/leases/`), so a
lease on one node says nothing about another. Keep one master per target: two masters driving the same
device do not see each other's leases.

## When no message arrives

Attach to the worker's session on the node: `ssh <node> -t tmux attach -t friday-<g>` (or
`tmux attach -t friday-<g>` if you are on it). Or open the session in the Claude app: the worker runs
with Remote Control and is named `<g>.<node>`. If the session is gone, check the goal's branch
`friday/<g>` on origin and the worktree on the node.
