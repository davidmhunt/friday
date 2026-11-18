# friday 1.0 specification

This is the one reference for what friday does: the model, the file formats, the status lifecycle,
every command, the execute workflow, every hook rule, what is enforced and what is advice, the
project config and the known limits. Other docs link here instead of repeating it:
[workflow.md](workflow.md) (a walkthrough), [fleet.md](fleet.md) (nodes and dispatch),
[dashboard.md](dashboard.md) (the status page), [runtime.md](runtime.md) (`./run`).

Where this page and the code disagree, the code wins and this page has a bug; `tests/test_spec.py`
fails on the disagreements it can detect (commands, flags, header keys, statuses, exit codes, hook
rules).

Contents: [1 Model](#1-model) | [2 Formats](#2-formats) | [3 Lifecycle](#3-status-lifecycle) |
[4 Who may change what](#4-who-may-change-what) | [5 Pre-approved commands](#5-pre-approved-commands-allowed-commands) |
[6 Amendments and change sets](#6-plan-amendments-and-a-directives-change-set) | [7 Commands](#7-commands) |
[8 Workflow](#8-the-execute-workflow) | [9 Hooks](#9-hooks) | [10 Enforced versus advice](#10-enforced-versus-advice) |
[11 Project config](#11-project-config-claudefridayjson) | [12 Fleet and dash](#12-the-fleet-and-the-dash) |
[13 Known limits](#13-known-limits)

## 1 Model

Work is a **goal**, split into **directives**, split into **steps**.

| Unit | File | Branch | Done when | Lands as |
|---|---|---|---|---|
| Goal | `docs/goals/<goal>.md` | `friday/<goal>` | every directive is `done` and reverified | one PR into its Base, by `friday land --goal <g>` |
| Directive | `docs/directives/<id>.md` | the goal branch; `friday/<id>` when `Land: pr` | its `Verify:` command passes and an independent verifier agrees with its steps and `## Acceptance` | commits on the goal branch (`Land: goal`), its own PR (`pr`), nothing (`none`) |
| Step | a numbered item of `## Steps` | the goal branch | covered by the directive's Verify | one commit, only if tracked files changed |

- A goal is one planning run (`/friday:plan`), one approval, one branch and one PR. Its **Base** is
  the branch the PR targets and the branch where the plan lives (section 6).
- Directives of a goal run in the listed order, one at a time. Parallelism is across goals
  (separate branches, worktrees or machines), never within a goal.
- A directive has a **Deliverable** (`code`, `doc`, `slides`, `external`) that decides how it is
  verified and reviewed, and a **Land** field that decides what is pushed.
- Every commit made during a directive ends with the line `Directive: <id>`. `friday finish`
  adds one record commit per directive (Status and Log).
- A directive that only reproduces, measures or inspects commits nothing: it appends to the
  untracked `runs/<id>/notes.md` (keep `runs/` in `.gitignore`), and `friday finish` copies the
  notes into the Log.
- Squash-merging the goal's PR is recommended (one commit on Base per goal); friday never changes
  repository settings.

## 2 Formats

Both files are Markdown. `friday check` validates them, `friday parse --json` prints them parsed,
and a PostToolUse hook validates a file each time it is written. Errors block (`friday check` exits
1, the hook sends them back to the model); warnings are only reported.

First line of both: `# <name>: <title>`. The name equals the filename stem; the title is non-empty.
Header lines are `Key: value` lines before the first `## `; backticks around a value are
stripped; each key may appear once (a duplicate is an error). Sections are `## ` lines; fenced code
blocks are not scanned for them. Numbered lists are `1.`, `2.`, ... with no gaps; indented lines
continue an item; any other non-blank unindented line in the section is an error.

### 2.1 Directive file

```markdown
# core-03: Reject cfgs whose chirp range exceeds the board limit
Status: proposed
Goal: board-limits
Node: any
Deliverable: code
Land: goal
Accept: auto
Verify: ./run tools/check.sh && ./run uv run pytest tests/test_cfg_limits.py -q
Hardware: none

## Goal
The result, and how a reader can tell it holds.

## Steps
1. Name files and interfaces.
2. [heavy] A harder step. Heavy because: a new numerical method.

## Acceptance
- A checkable statement about the deliverable.

## Review
- What the user should open and what to look for (needed with `Accept: user`).

## Allowed commands
- `friday dispatch --goal board-limits`

## Out of scope
- What this directive must not touch.

## Log
```

The id matches `^[a-z0-9][a-z0-9_-]*-\d{2,}$` (for example `core-03`) and the filename stem.

| Header key | Required | Allowed values |
|---|---|---|
| `Status` | yes | `proposed`, `approved`, `running@<host>`, `awaiting review`, `done`, `blocked: <reason>` (non-empty reason) |
| `Goal` | yes | a goal name, `^[a-z0-9][a-z0-9-]*$` |
| `Node` | yes | `any`, `tag:<x>`, `host:<x>` |
| `Deliverable` | yes | `code`, `doc`, `slides`, `external` |
| `Land` | no (default `goal`) | `goal`, `pr`, `none` |
| `Accept` | no (default `auto`) | `auto`, `user` |
| `Verify` | yes | one shell command run from the repo root; not empty. `none` only for `external` |
| `Hardware` | yes | `none`, or the resources the directive touches; not empty |

An unknown header key is a warning.

| Section | Required | Rules |
|---|---|---|
| `## Goal` | yes | the result and how to tell it holds |
| `## Steps` | yes | numbered list; at least one step. A `[heavy]` step (the marker inside an inline code span is only a mention) must contain `Heavy because:`; heavy steps run on Opus |
| `## Acceptance` | `doc`, `slides`, `external`: yes; `code`: optional | at most once; at least one `- ` bullet where required; the verifier grades each bullet |
| `## Review` | with `Accept: user`: yes | at most once; at least one `- ` bullet; printed when the directive reaches `awaiting review` |
| `## Allowed commands` | no | bullets, each with exactly one backticked pattern (section 5) |
| `## Out of scope` | yes | what must not change; the verifier checks it |
| `## Log` | yes, last | written by commands, never by hand |

`## Goal`, `## Steps`, `## Out of scope` and `## Log` are required once each, in that order, with
`## Log` last; other sections may sit anywhere before `## Log`. A missing, duplicated or misplaced
required section is an error.

Rules that tie keys together:

- `Deliverable: external`: `Verify` must be `none` and `Land` must be `none` (an omitted `Land`
  defaults to `goal` and so fails). `external` should use `Accept: user` (a warning otherwise).
- `Verify: none` for any other deliverable is an error.
- `Accept: user` requires `## Review`.
- A `doc`, `slides` or `external` directive requires `## Acceptance`.
- Cross-checks with the goal file: the file named by `Goal:` must exist and list this directive
  (errors); a directive `done` while an earlier one in its goal is not, and a directive `approved`
  while its goal is still `proposed`, are warnings.
- A warning when `Verify` matches a `hardware` pattern of `.claude/friday.json`: Verify is re-run
  unattended (fix rounds, landing) without the hardware prompt. Run the device step once, record it
  with `friday result write`, and make Verify a `friday result check`.

### 2.2 Goal file

```markdown
# board-limits: Enforce board limits in cfg validation
Status: proposed
Base: main
Land: pr

## Goal
What the goal delivers and how a reader can tell it holds.

## Directives
1. core-03: Reject cfgs whose chirp range exceeds the board limit
2. core-04: Document the limits

## Log
```

The goal name matches `^[a-z0-9][a-z0-9-]*$` and must not look like a directive id (the branch
`friday/<goal>` would collide with `friday/<id>`).

| Header key | Required | Allowed values |
|---|---|---|
| `Status` | yes | `proposed`, `approved`, `running`, `done`, `blocked: <reason>` (a goal is never `running@<host>` or `awaiting review`) |
| `Base` | yes | the branch the PR targets; not empty |
| `Land` | yes | `pr`, `none` |

Unknown goal headers are ignored. Sections `## Goal`, `## Directives`, `## Log` are required once
each, in that order, `## Log` last; others are not restricted. `## Directives` is a numbered list in
run order; each item starts with a directive id, optionally followed by `: <text>`. A bad or repeated
id, or an id with no directive file whose `Goal:` names this goal, is an error.

### 2.3 Other files friday writes

- `results/<id>.json`, tracked, by `friday result write`: metrics, each file's `sha256` and size,
  the command, `commit` (HEAD), `dirty`, `node`, `time`.
- `runs/<id>/notes.md`, untracked: a step's findings when it commits nothing.
- `<git dir>/friday-active`, per worktree, never committed: the active marker (`id`, `host`,
  `started`, `gate`, `base`, `goal_base`), written by `friday start`, removed by `friday finish`.
- `~/.local/state/friday/leases/<resource>.json`: hardware leases (section 9.3).
- `~/.local/state/friday/dispatches.jsonl` on the master: one line per dispatch or resume.

## 3 Status lifecycle

Directive:

```
proposed --(user approves)--> approved --(execute)--> done
                                  |                     ^
                                  |  Accept: user       | friday accept
                                  +--> awaiting review -+
                                  |            | friday accept --reject REASON
                                  +--> blocked: <reason> <------+
                                         | friday unblock
                                         +--> approved
```

| Status | Meaning | Set by |
|---|---|---|
| `proposed` | written by the plan, not yet approved | `/friday:plan` |
| `approved` | the user approved it; it may start. It stays `approved` while it runs (`friday start` commits nothing); `friday status` shows `running@<host>` from the active marker | the user; `friday unblock` |
| `running@<host>` | accepted by the format check for a hand-set status; the commands never write it | |
| `awaiting review` | work finished, Verify and review passed, `Accept: user`: the user must open the `## Review` bullets and run `friday accept`. The goal branch is pushed and later directives continue | `friday finish` |
| `done` | finished | `friday finish` (`Accept: auto`), `friday accept` |
| `blocked: <reason>` | stopped for the user: a step needs a decision, Verify keeps failing, review gaps remain, a rejection | `friday finish --blocked`, `friday accept --reject` |

Goal: `proposed` -> `approved` (the user) -> `running` (`friday start` of its first directive) ->
`done` (`friday land --goal`). `friday finish --blocked` or `friday accept --reject` sets the goal to
`blocked: <id>`; `friday unblock` sets it back to `running`. `friday land --goal` refuses (exit 7)
while any directive is not `done`, `awaiting review` included.

A directive starts only when its status is `approved` or `running...`, its files have no format
errors, and every earlier directive of its goal is `done` or `awaiting review`.

## 4 Who may change what

| Who | May |
|---|---|
| The user | approve a goal and its directives (`proposed` -> `approved`); run `friday accept` (the only way out of `awaiting review`); merge PRs; run the prompted commands (`friday release`, a real `friday dispatch`, a real `friday nodes --clean`) unless a directive pre-approves them; run `sudo` and other denied commands |
| `/friday:plan` | write goal and directive files as `proposed`, run `friday init`, commit the plan on Base |
| Commands | write `Status` and `## Log`: `start` (goal `approved` -> `running`), `finish`, `accept`, `unblock`, `land --goal` (goal `done` and a Log line). Each writes one commit with a `Directive: <id>` or `Goal: <g>` line |
| Agents in a run | edit code, docs and data inside a step's scope, and `runs/<id>/notes.md`; never `Status` or `## Log` by hand; never `friday accept` (the PreToolUse hook denies it, also through `ssh`, `bash -c`, `uv run`) |

A change to a directive's header or `## Allowed commands` after approval is a plan amendment
(section 6); an edit on the goal branch cannot widen what a run may do.

## 5 Pre-approved commands (`## Allowed commands`)

A directive may list commands that run without a prompt while it is the active directive. This is
how an unattended or dispatched run gets past the commands that would otherwise ask the user
(`friday dispatch`, `friday nodes --clean`, `friday release`, a hardware command).

```markdown
## Allowed commands
- `friday nodes --clean alfred`
- `ssh rover ./run ros2 topic list`
- `./run tools/bench.sh *`
```

- **Format.** Bullets each holding exactly one backticked pattern. `*` matches any text; the whole
  command must match. A pattern is one simple command.
- **Where the list is read from.** The hook reads the directive as committed on `origin/<Base>`
  (`git show origin/<Base>:docs/directives/<id>.md`), the plan the user approved, never the working
  tree. `<Base>` comes from the active marker, is trusted only when the goal file on `origin/<Base>`
  names the same Base, and is never a `friday/*` branch. So editing the directive or the goal's
  `Base:` on the goal branch cannot widen the list. To change the list, amend the plan on Base and
  push it (section 6); `friday start` fetches `origin/<Base>`, the hook never does.
- **Scope.** Only the active directive's list applies (the marker names it), only to a command
  that is a single simple command (no `&`, `;`, `|`, backticks, `$(`, `<(`, `>(`, or newlines), and
  only in the worktree where the directive is active.
- **`friday check` errors** on a pattern that is only `*`, contains `&&`, `;`, `|`, a backtick or
  `$(`, starts with `friday accept`, or matches the hook's deny list.
- **What it overrides.** Only the permission prompt. It answers `allow` where Claude Code would
  ask.
- **What still applies.** The deny list wins (so `sudo` is refused even when listed, and `sudo` on
  a robot over `ssh` stays a step the user does); so do the `friday accept` guard, the `run_only`
  rule, the push guard, the commit guard (a commit on main or Base is still denied or asked), and
  hardware leases (a pre-approved hardware command still takes the lease and is still denied while
  another session holds it).
- **What still prompts.** Everything else that is not allowed by `.claude/settings.json` or the
  user's own Claude Code permissions. The friday allow rules in `.claude/settings.json`
  (`friday init` merges them) cover `status`, `new`, `check`, `parse`, `start`, `verify`,
  `finish`, `commits`, `result`, `land`, `init`, `session-end`, `nodes`, `nodes --check`,
  `nodes --clean <node> --dry-run` and `dispatch --goal <g> --dry-run`. A real `dispatch`, a real
  `nodes --clean` and `release` are prompted on purpose and run unattended only when a directive
  lists them. `friday accept` can never be allowed.
- While a directive is active, `git push` may update only the goal's own branch (`friday/<goal>`,
  or `friday/<id>` for `Land: pr`), so the agent cannot edit `origin/<Base>` into a trusted source.

## 6 Plan amendments and a directive's change set

**Amending a running goal's plan.** The plan lives on the goal's Base. To change an approved goal
or directive (steps, Verify, `## Allowed commands`, a new directive), commit the change on Base,
check it with `friday check`, and push Base. Never edit the plan on the goal branch: `friday start`
merges Base into the goal branch before each directive (`origin/<Base>` after a fetch with a 30 s
limit; a failed fetch warns and uses the local Base). A merge conflict aborts the merge and `start`
exits non-zero. The running session sees an amendment only at its next `friday start`: before the
next directive, or when the current directive is restarted (for example after a block and
`friday unblock`). An amendment to the running directive does not reach the session that is
executing it. While a directive is active, the `commit-msg` git hook refuses a commit without
`Directive: <id>`, except a commit that only touches goal and directive files and names a directive
of the same goal.

**A directive's change set.** `friday commits <id>` finds it: the non-merge commits between the
merge-base of the goal's Base and the tip (HEAD, or `friday/<id>` for `Land: pr` when that branch
exists) that carry a `Directive: <id>` line, minus friday's own record commits (`<id>: blocked`,
`unblock`, `record results`, `accepted`). Commits on that range with no `Directive:` line that touch
anything outside `docs/goals/` and `docs/directives/` are listed as `untracked`; the review treats
each as a gap. The review and the Log's commit list use this set, so a restart never changes what
is reviewed.

## 7 Commands

`friday <command> ...` (put it on PATH with `friday install`; `python3 <checkout>/bin/friday`
also works). Exit codes: 0 success; a refusal with a message (for example "uncommitted changes",
"no directive") exits 1 unless the table says otherwise; a usage error from the parser exits 2.
`friday --help` lists every command.

| Command | What it does | Exit codes |
|---|---|---|
| `friday status [--json] [--push] [--to URL] [--node NAME]` | directives and goals in this repo, the active one, awaiting-review ones, leases. `--json`: one node snapshot. `--push`: post the snapshot to the dash (`--to URL` overrides the master's `[dash]` port). `--node NAME` names the snapshot's node. `--to` without `--push` is refused | 0; `--push` 1 when the push fails |
| `friday init` | install the `commit-msg` guard and merge the friday allow rules into the repo's tracked `.claude/settings.json` (never `settings.local.json`); commits nothing | 0; 1 unreadable settings file |
| `friday new <loop>` | print the next free directive id for a loop (`core` -> `core-04`) | 0 |
| `friday start <id> [--no-gate]` | check the directive and its goal, enforce goal order, switch to `friday/<goal>` (`friday/<id>` for `Land: pr`), merge Base, set the goal `running`, install the guard, write the marker, print `base <sha>`. Commits nothing. `--no-gate` turns the Stop-hook Verify gate off for this directive | 0; 1 refused (not approved, format errors, earlier directive not done, dirty tree, merge conflict) |
| `friday verify [<id>]` | run the directive's `Verify` (default: the active one); `none` is skipped | Verify's own exit code; 0 for `none`; 1 no directive |
| `friday finish <id> [--verify TEXT] [--review TEXT] [--base SHA] [--blocked REASON]` | append the Log entry (commits, notes, Verify, review) and set Status: `done`, `awaiting review` (`Accept: user`) or `blocked: REASON` (goal also blocked); one commit; clear the marker. `--base SHA` lists commits since SHA instead of using `friday commits` | 0; 1 other tracked files uncommitted, commit failed |
| `friday accept <id> [--note TEXT] [--reject REASON]` | the user accepts an `awaiting review` directive (`done`) or rejects it (`blocked: REASON`, goal blocked); one commit; must run on the directive's branch. Denied to agents | 0; 1 not awaiting review, wrong branch |
| `friday unblock <id>` | a `blocked:` directive back to `approved` with a Log line, and a blocked goal to `running`; one commit; on the directive's branch | 0; 1 not blocked, wrong branch |
| `friday commits <id> [--json]` | the directive's own commits and `untracked` commits (section 6); `--json` gives `base`, `commits`, `untracked` | 0 commits found; 3 none; 2 cannot say (no goal, no Base branch, no merge-base) |
| `friday land <id> [--goal G] [--base BRANCH]` | by `Land`: `pr` pushes `friday/<id>` and opens its PR into the goal's Base (or `--base`); `goal` pushes `friday/<goal>`, no PR; `none` pushes nothing. `friday land --goal <g>` reverifies every directive, marks the goal `done` (one commit), pushes `friday/<g>`, opens or updates the goal's PR with a table of directives. Runs on the branch being landed, with a clean tree | 0 done (a PR line `PR: <url>`); 3 push failed; 4 pushed, Base not on origin; 5 pushed, no PR (`gh` missing or signed out; prints `COMPARE: <url>`); 6 (`--goal`) a Verify failed, nothing pushed; 7 (`--goal`) a directive is not done, ids printed, nothing run or pushed; 1 other refusal |
| `friday release <resource>` / `friday release --all` | free a hardware lease | 0; 1 no resource named |
| `friday result write <id> [--metric K=V]... [--file PATH]... [--cmd TEXT] [--note TEXT]` | record an expensive run once in `results/<id>.json` | 0; 1 error (no HEAD, file missing) |
| `friday result check <id> [--require 'K OP V']... [--files]` | the cheap Verify: the record exists, its commit is an ancestor of HEAD, each requirement holds (`OP` is one of `>= > <= < == !=`), with `--files` each recorded file still has its hash | 0 holds; 1 one line per unmet condition |
| `friday check [<id> \| --goal G \| --all]` | validate goal and directive files (default all) | 0; 1 any error |
| `friday parse <id> --json` / `friday parse --goal G --json` | the parsed file as JSON, with `errors` and `warnings`; includes `allowed` for a directive | 0; 1 the file has errors; 2 file missing |
| `friday nodes [--check]` | list the fleet registry; `--check` probes each node over ssh and the dash | 0; 1 no registry, or a master or worker failed the check |
| `friday nodes --setup NODE [--yes]` | set the node's first-run prompt skips in its `~/.claude/settings.json`, write its `node.toml`, link `friday`, install the 30 s push timer; asks y/N (`--yes` skips, required without a terminal) | 0; 1 refused or failed |
| `friday nodes --clean NODE [--dry-run]` | remove finished goals' worktrees, branches, tmux sessions and trust entries on a node; `--dry-run` only plans | 0; 1 error; `--dry-run` without `--clean` exits 2 |
| `friday dispatch --goal G [--node N] [--report-to S] [--dry-run]` | check, pick a node, prepare a worktree there and start a tmux session `friday-<G>` running the goal's directives; records it. `--dry-run` changes nothing | 0; 10-27 a refusal on the master (table below); 30-36 a refusal by the node; 1 launch failed |
| `friday dispatch --goal G --resume [--unblock ID]... [--node N] [--report-to S] [--dry-run]` | restart a stopped goal in its existing worktree; `--unblock ID` (repeatable) first runs `friday unblock ID` there | 0; 16, 18, 19, 20; 21-26 (table below); 1 stop or launch failed |
| `friday session-end --goal G` | close this dispatched session's own tmux session 10 s later, once the goal is `done` | 0; 1 refused (not dispatched, not that session, goal not done) |
| `friday install [--bin-dir DIR]` | link `DIR/friday` (default `~/.local/bin`) to this checkout | 0; 1 would overwrite something else |
| `friday uninstall [--bin-dir DIR]` | remove that link when it points at a friday checkout, and this repo's `commit-msg` guard | 0; 1 not a friday link |
| `friday dash [--bind ADDR]... [--no-self]` | serve the status API on 127.0.0.1 and the tailnet address (section 12) | 0; 1 |
| `friday dash up` / `friday dash down` | start or stop the dash as a Docker Compose service | docker's exit code; 1 docker or registry missing |

`friday result write` exists so an expensive or hardware run is done once and Verify stays cheap:
`Verify: friday result check <id> --require 'accuracy >= 0.9' --files`.

### 7.1 Dispatch exit codes

Master-side refusals print a one-line reason and a fix on stderr.

| Exit | Kind | Cause |
|---|---|---|
| 10 | goal | no such goal, or its Status is not approved or running |
| 11 | format | `friday check --goal <g>` reports errors |
| 12 | directives | a directive file is missing, nothing remains, or the first remaining directive is not approved |
| 13 | land-pr | a remaining directive has `Land: pr`; run it locally with `/friday:execute` |
| 14 | unpushed | no origin, or the goal or directive files are uncommitted or differ from the source ref on origin |
| 15 | plugin | the friday folder is not a git clone, or its HEAD is not on its origin |
| 16 | registry | no nodes file, or it is invalid |
| 17 | route | no node satisfies every remaining directive's `Node:` line |
| 18 | node | `--node` names a missing node or a target |
| 19 | unreachable | the chosen node did not answer over ssh |
| 20 | report-to | no `--report-to` and no `report_to` in the registry |
| 21 | no-record | `--resume`: no dispatch record for the goal and no `--node` |
| 22 | no-worktree | `--resume`: the worktree is missing or not on `friday/<g>` |
| 23 | goal-done | `--resume`: the goal is done, or nothing is left to run |
| 24 | busy | `--resume`: session `friday-<g>` exists and is not idle at a prompt |
| 25 | blocked | `--resume`: a remaining directive is blocked and not named by `--unblock` |
| 26 | unblock | `--unblock` names a directive not in the goal, or the reset failed |
| 27 | settings | the source ref's `.claude/settings.json` lacks a friday allow rule; run `friday init`, commit and push |
| 30 | untrusted | node: `repos` is not trusted in `~/.claude.json` |
| 31 | session | node: tmux session `friday-<g>` already exists |
| 32 | origin | node: the clone's origin is missing or differs from the master's |
| 33 | worktree | node: the worktree path already exists (use `--resume`) |
| 34 | branch | node: local branch `friday/<g>` already exists in the clone |
| 35 | plugin | node: cannot check out the plugin commit at `plugin_dir` |
| 36 | git | node: clone, fetch or worktree add failed |

## 8 The execute workflow

`/friday:execute <id>` runs `workflows/execute.js` in the background (watch it with `/workflows`).
It runs one agent at a time. Each friday command is run as its own single Bash call so the repo's
allow rules match it.

1. **Prepare.** `friday parse <id> --json` (errors stop the run), then `friday start <id> --no-gate`
   (goal branch, goal order, Base merge, marker). Nothing is committed.
2. **Implement.** One `implementer` agent per step, in order; `[heavy]` steps run on Opus. A step
   commits only if it changed tracked files, last line `Directive: <id>`. A step that needs a
   decision or fails stops the run as blocked.
3. **Verify.** The `runner` agent runs `Verify`. On failure an implementer fixes the root cause and
   it runs again, up to 4 rounds or until the same failure repeats twice. Skipped for
   `Deliverable: external`.
4. **Review.** The `verifier` (Opus, read-only, fresh context) runs `friday commits <id>`, reviews
   each commit and the touched files against the steps, `## Acceptance` and `## Out of scope`, and
   reports every untracked commit as a gap. Real gaps get one fix round, then Verify and a second
   review; gaps that remain block.
5. **Land.** `friday finish <id> --verify ... --review ...` writes the record. Then by `Land`:
   - `goal`: `friday land <id>` pushes `friday/<goal>`. If this directive is `Accept: user`, the
     workflow stops at `awaiting review` and skips `land --goal`. Otherwise, if it was the last
     directive of the goal, the workflow runs `friday land --goal <goal>`, which opens the goal's
     PR, or exits 7 if an earlier directive is not yet done (for example still `awaiting review`).
     If it was not the last, the workflow names the next directive.
   - `pr`: `friday land <id> --base <Base>` pushes `friday/<id>` and opens that directive's own PR.
   - `none`: nothing is pushed.

Any stop sets `Status: blocked: <reason>` through `friday finish --blocked` and ends the run; work
already committed stays. Fix or answer, run `friday unblock <id>`, and run `/friday:execute <id>`
again.

**When the goal's PR opens by itself.** At the end of the last directive of a goal, when that
directive is `Land: goal` and `Accept: auto`, its Verify and review pass and the push succeeds (a
dispatched session does this too). The workflow does not look at earlier directives: if one is
still `awaiting review`, `friday land --goal` exits 7 and no PR opens; if you already accepted it,
the PR opens. **When you run `friday land --goal <g>`:** after
any directive was `awaiting review` and you ran `friday accept` (the goal PR is never opened for
you while a review is pending); when the last directive is `Land: pr` or `none`; when a landing
step exited 3, 4, 5, 6 or 7 (the output says why); and when you ran directives by hand.
`friday land --goal` on a goal with `Land: none` marks it done and pushes nothing.

**Without the workflow.** For hands-on work run a directive in your own session:
`friday start <id>`, work, `friday finish <id>`. While a directive is active, the Stop hook runs its
`Verify` each time Claude tries to end a turn (section 9.2).

**Dispatched runs.** `friday dispatch --goal <g>` starts a session on a node that runs the goal's
directives in order and sends the master `done <g> PR <url>`, `review <g> <ids> PR-pending` or
`blocked <g> <id>: <reason>`. It has no human at the prompt, so every command that would prompt
must already be allowed, by `.claude/settings.json` or by `## Allowed commands` (section 5).

## 9 Hooks

Hooks are in `hooks/hooks.json` and run `hooks/friday_hook.py`. Each decision is deterministic and
its reason tells the agent the fix. A hook bug fails open: it prints an error to stderr and makes no
decision rather than wedge a session. Rules in a PreToolUse run are combined: `deny` beats `ask`
beats `allow`.

### 9.1 PreToolUse (matcher Bash)

| Rule | Effect |
|---|---|
| Deny list | deny the commands listed in the next table |
| `friday accept` guard | deny `friday accept` in any form an agent might run it: direct, `python3 .../bin/friday`, `uv run`, inside `ssh host '...'`, `bash -c '...'`, `docker`, `xargs`, `eval`, `watch`, `env`, up to 4 levels |
| `run_only` | with `.claude/friday.json`, deny a bare `python`, `uv`, `cmake`, ... (the `run_only` list) and name the `./run` form |
| Push guard | while a directive is active, deny any `git push` that is not an explicit push of the goal's own branch (`friday/<goal>`; `friday/<id>` for `Land: pr`), including `--all`, `--mirror` and an unjudgeable target |
| Commit guard | while a directive is active, deny `git commit` on main, master or the goal's Base (create or switch to `friday/<goal>`); with no directive active, ask before a commit directly on main or master. The repository judged is the one the command commits in (`cd DIR && git commit`, `git -C DIR commit`) |
| Pre-approval | allow a single simple command that matches the active directive's `## Allowed commands` as committed on `origin/<Base>` (section 5) |
| Hardware | a command matching a `hardware` pattern of `.claude/friday.json`: deny when another session holds the resource's lease; otherwise take the lease and ask the user (allow when pre-approved) |

The deny list, each rule traced to an incident or a hard rule:

| Label | Refuses |
|---|---|
| `sudo` | `sudo`, `su`, `doas` anywhere in the command, including after `ssh host` |
| `chmod 777` | `chmod 777` and `chmod a+rwx` |
| `rm -rf` | an unscoped recursive force remove of `/`, `~`, `.`, `..` or a bare `*` |
| `force-push` | `git push` with `--force`, `--force-with-lease` or `-f` |
| `+refspec` | `git push` of a `+ref` refspec |
| `push to main` | `git push` to `main` or `master` |
| `git remote add` | adding a git remote |
| `git clean -f` | `git clean` with `-f` or `--force` |
| `curl pipe sh` | piping `curl` or `wget` output into `bash`, `sh` or `zsh` |
| `eval fetched` | `eval` of command substitution that fetches with `curl` or `wget` |
| `raw disk write` | `mkfs`, `mkfs.*`, `dd if=` |

### 9.2 Other Claude Code events

| Event | Matcher | Effect |
|---|---|---|
| PostToolUse | `Write`, `Edit`, `MultiEdit` | validate the edited goal or directive file under `docs/goals/` or `docs/directives/` (not `README.md`, `TEMPLATE.md`); its own format errors go back to the model (exit 2); warnings and clean files are silent |
| Stop | all | the Verify gate: while a directive is active here with the gate on (no `--no-gate`) and no background task is running, run its `Verify` (up to 30 minutes). On failure block the stop with the output tail, up to 3 times, then stop for the user. `Verify: none` is reported, not run |
| SessionEnd | all | release this session's hardware leases |

### 9.3 Hardware leases

`~/.local/state/friday/leases/<resource>.json` records the session, host, time and the command. One
session holds a resource at a time. The lease is taken when the prompt is shown, not when the user
answers it; it expires after 4 hours, ends with the session, and is freed by hand with
`friday release <resource>`.

### 9.4 The git `commit-msg` guard

`friday init` and `friday start` install a `commit-msg` hook in the repo's hooks directory
(an existing foreign hook is kept as `commit-msg.local` and still runs first; if both exist the
guard is not installed and friday warns). While a directive is active in the worktree, git refuses
a commit whose message lacks the line `Directive: <id>`, for every committer, not just agents. A
commit that stages only `docs/goals/` and `docs/directives/` files is accepted when it names a
directive of the same goal. `git commit --no-verify` skips the guard on purpose; the agent's
PreToolUse hook does not prevent it, and `friday commits` shows such a commit as `untracked`.
`friday uninstall` removes the guard and restores `commit-msg.local`.

## 10 Enforced versus advice

**Enforced** (deterministic, cannot be argued with by the model):

- the file formats (`friday check`, the PostToolUse hook, and `friday start` and `dispatch`
  refusing files with errors);
- goal order, approved-only starts, and the exit codes of `land` and `dispatch`;
- the deny list, the `friday accept` guard, `run_only`, the push guard, the commit guard, hardware
  prompts and leases, pre-approval scope (all PreToolUse);
- the `Directive:` line on every commit during a directive (the git `commit-msg` hook; bypassable
  only with `git commit --no-verify`, which `friday commits` then exposes);
- the Stop-hook Verify gate in a session run without `--no-gate`;
- `friday land --goal`: every directive `done` and reverified before a push.

**Advice** (instructions in skills, agent prompts and docs; nothing stops a deviation):

- planning style: interview, small steps, a Verify that proves the Acceptance;
- the `hardware` skill (leases are enforced, the discipline around power cycles and cables is not);
- run-once-then-record (`friday result`) for expensive runs: no hook forces it, `friday check` only
  warns when Verify matches a hardware pattern;
- `runs/<id>/notes.md` untracked and `runs/` in `.gitignore` (`friday start` warns);
- squash-merge, one commit per step, and not editing the checkout loaded as the plugin;
- the verifier's judgment (it is an agent; its verdict is recorded, not proven);
- `Node:` and `Hardware:` header values (only `Node:` routes a dispatch; `Hardware:` is read by
  people).

## 11 Project config (`.claude/friday.json`)

Optional, at the repo root. Without it only the deny list, the accept guard, the push and commit
guards and pre-approval apply. A missing or unparsable file is read as empty.

| Key | Meaning | Default |
|---|---|---|
| `run_wrapper` | the command builds, tests and scripts must go through | `./run` |
| `run_only` | tool names (`python`, `uv`, `cmake`, ...) that must be run through the wrapper | none |
| `hardware` | object: resource name -> list of regular expressions matched against a Bash command | none |

```json
{
  "run_wrapper": "./run",
  "run_only": ["python", "python3", "uv", "pytest", "cmake", "make", "colcon"],
  "hardware": {
    "radar-bench": ["\\bradar_cli\\b", "/dev/ttyUSB\\d", "\\bdca1000\\b"],
    "host-config": ["\\bip\\s+link\\b", "\\bethtool\\b"],
    "ground-bot": ["\\bssh\\b.*\\bground-bot\\b"]
  }
}
```

Friday also reads the repo's tracked `.claude/settings.json` (the allow rules, merged by
`friday init`) and, on the master, the fleet registry `nodes.toml` ([fleet.md](fleet.md)).

## 12 The fleet and the dash

**Fleet.** A goal whose directives' `Node:` lines this machine does not satisfy runs on another
machine: `friday dispatch --goal <g>` prepares a worktree on a node over Tailscale SSH and starts a
Claude session in tmux there (Remote Control on); the session messages the master when the goal
lands or a directive blocks. Nodes are `master`, `worker` or `target` (SSH only, never runs
Claude), listed in `nodes.toml`. Registry keys, routing, one-time node setup, `--resume`,
cleaning and refusals: [fleet.md](fleet.md).

**Dash.** `friday dash` on the master serves a read-only status page and API on 127.0.0.1 and the
master's tailnet address (never `0.0.0.0`), collecting each node's `friday status --json` pushed
every 30 s by a systemd user timer. Awaiting-review directives and blocked goals appear as needing
the user. How machines and projects appear, the API and the Docker deployment:
[dashboard.md](dashboard.md).

## 13 Known limits

- **The deny list matches inside `ssh`.** The rules see the whole command line, so `ssh robot sudo
  reboot` is denied. The deny list also wins over pre-approval, so `sudo` on a robot over `ssh`
  stays a step the user does, even if a directive lists it.
- **A hardware prompt in a dispatched session has nobody to answer it.** The session waits, and a
  resume (`--resume`) is needed unless the commands are pre-approved in `## Allowed commands`.
- **Landing is GitHub pull requests only** (`gh`; the compare URL covers a missing `gh`). No GitLab
  or other forge, and no merge: the user merges.
- **The lease is taken when the prompt is shown** and expires after 4 hours; a command the user
  then declines still leaves the lease until it expires, the session ends or `friday release`.
- **Verify runs up to 30 minutes** in the Stop hook (and the hook entry allows 1900 s). A longer
  check belongs in `friday result` (run once, check cheaply).
- **friday's git and `gh` calls time out after 180 s**; the Base fetch in `friday start` after
  30 s (it then warns and uses the local Base).
- **Pre-approval reads `origin/<Base>` as last fetched.** A plan amendment that is not pushed, or
  not yet fetched by a `friday start`, is not seen by the hook.
- **Goal directives run in sequence.** Parallel directives within a goal are not built.
- **A dispatched goal runs on one node** and cannot move to another.
- **Parallelism is across goals**, not within one: separate branches, worktrees or machines. A
  workflow runs one agent at a time unless it carries its own limit (Claude Code caps a workflow at
  min(16, CPUs-2) agents and the cap is not configurable).
- **A host with ROS 2 sourced breaks pytest collection** through its `launch_testing` plugin. Run
  pytest with `-p no:launch_testing -p no:launch_ros` (friday's `pytest.ini` does).
- **A PR's Base branch must exist on origin**, or `friday land` exits 4.
- **`--no-verify` skips the commit guard**; `friday commits` shows the commit as `untracked`.
- **A hook failure fails open.**
