# friday v1 handoff: state on 2026-11-17 and what comes next

Written for a Claude Code session on David's machine that continues this work with no other
context. Read it fully before acting. The original design spec is a claude.ai doc
("friday v1 — design spec", https://claude.ai/artifact/UJA3CnFtrrbW3ALv1DWdCy); everything a
session needs from it is restated here.

## 1. What friday v1 is

A Claude Code plugin (this repo, branch `v1`; v0.20 is tag `v0.20.0`). The top-level session on
Fable or Opus is the orchestrator. `/friday:plan` turns a goal into directives
(`docs/directives/<loop>-<NN>.md`, each with an executable `Verify:` line); the user approves once
per goal; `/friday:execute <id>` (a workflow) implements, verifies, reviews and opens a PR.
Deterministic hooks enforce what must never bend. See `README.md`, `docs/workflow.md`,
`docs/runtime.md`, `docs/migrating-from-v0.md`, `CHANGELOG.md`.

## 2. Decisions already made (don't reopen without the user)

| Topic | Decision |
|---|---|
| Tools | Claude Code only; the Antigravity adapter is gone |
| Autonomy | Mostly autonomous: approve per goal, review PRs; hardware is the one per-command stop |
| Users | Solo (David), several parallel loops |
| Models | Planning session on Fable; workers/implementers Sonnet (Opus for `[heavy]` steps); verifier Opus; runner Haiku |
| Records | Tracked directive files + PRs; no GitHub-issues mirror |
| Repo | friday v1 on branch `v1` of this repo; v0.20 kept as tag `v0.20.0`; `v1` replaces `main` once proven |
| Runtime | Claude on the host; code through `./run` into a dev container (uv inside), native where a machine needs it |
| Machines | Ubuntu laptop (ThinkPad P15v3), lab GPU workstation, robot/embedded computers; all on Tailscale |
| Robots | Plain SSH targets: no Claude session on them |
| Status view | Claude app (Remote Control) for live questions + one static page served on the tailnet; no third-party relay |
| Concurrency | Workflows run one agent at a time unless a workflow says otherwise; Claude Code's own cap is min(16, CPUs-2) per workflow and is not configurable, so any parallel workflow carries its own limit |

## 3. Current state

**friday** (branch `v1`, on top of `v0.20.0`): plugin manifest, hooks (`hooks/friday_hook.py`:
deny list, `./run` enforcement, hardware prompt + lease, commit trailer, Stop-time Verify gate,
SessionEnd lease release), agents (`implementer`, `verifier`, `runner`), skills (`plan`,
`directive`, `hardware`, `long-jobs`, `data-artifacts`), `workflows/execute.js`, `bin/friday`
(`status`, `new`, `start`, `verify`, `finish`, `land`, `release`), `lib/friday_core.py`.
51 tests pass; `claude plugin validate .` passes. Not yet on GitHub: the `v1` branch exists only on
the laptop. Push it (`git push -u origin v1`) when the user agrees.

**Goal model** (branch `friday/goal-model`, directives gm-01..gm-04): work is now goal -> directive
-> step. A goal (`docs/goals/<goal>.md`) owns one branch `friday/<goal>` and one PR; its directives
run in order on that branch and each is verified by its Deliverable type (code, doc, slides,
external). `bin/friday` gains `check`, `parse`, `land --goal` and exit code 6, and a PostToolUse
hook validates goal and directive files on write. The plan and directive skills, README,
`docs/workflow.md` and CHANGELOG describe it.

**CPSL_TI_Radar** (pilot, branch `friday-v1/runtime`, on GitHub): dev container + `./run` +
`tools/check.sh` (the default Verify), short `CLAUDE.md`, `.claude/friday.json` (hardware patterns
`radar-bench`, `host-config`), `.claude/settings.json` (allows the `friday` commands), firmware
skill, `docs/directives/`, v0.20 harness removed. First directive `bench-01` ran end to end on the
laptop; PR #112 (`friday/bench-01` -> `friday-v1/runtime`) is open for review.

## 4. Lessons from the first run (already fixed unless marked open)

- The Land step originally let an agent improvise `git push`/`gh`; nothing got published. Now
  `friday land <id> --base <base>` does it and returns 0 PR open, 3 push failed, 4 base not on
  origin, 5 gh missing or signed out (prints the compare URL).
- A PR's base branch must exist on GitHub. `friday-v1/runtime` was local-only at first.
- ROS 2 Jazzy is sourced in David's shells; its `launch_testing` pytest plugin breaks collection.
  Every Python repo needs `-p no:launch_testing -p no:launch_ros` (friday has it in `pytest.ini`).
- Patches applied with a glob picked up a duplicate download (`...(1).patch`). Prefer pushing
  branches over mailing patches now that work happens locally.
- Agent commits put `Directive: <id>` before or after `Co-Authored-By`; the hook accepts either.
- **Open:** the Stop-gate path (`friday start <id>` without `--no-gate`, in-session execution) has
  unit tests but has not been exercised in a live session.
- **Open:** whether a saved workflow starts when `/friday:execute <id>` is the first prompt passed
  on the command line (`claude "/friday:execute core-01"`). Phase 3 dispatch depends on it; check
  it first (step 0 below).

## 5. Phase 3: fleet dispatch

Goal: from the master session on one machine, run an approved directive on the machine that fits
its `Node:` line, in a fresh session, and hear back when it is done or blocked.

Design (from the spec; adjust if step 0 shows a Claude Code behaviour differs):
- **Node registry:** `~/.config/friday/nodes.toml` on the master only.
  ```toml
  [node.workstation]
  role = "master"          # master | worker | target
  ssh = "workstation"      # Tailscale MagicDNS name
  runtime = "container"    # container | native (sets FRIDAY_RUNTIME on that node)
  tags = ["gpu"]
  repos = "~/src"          # where clones live

  [node.laptop]
  role = "worker"
  ssh = "thinkpad"
  runtime = "container"

  [node.ground-bot]
  role = "target"          # SSH only, no Claude
  ssh = "ground-bot"
  runtime = "native"
  tags = ["radar-iwr1843", "dca1000"]
  ```
- **Routing:** `Node: any` -> any worker (prefer the one with fewest running directives);
  `tag:x` -> a worker or master with tag x, or, when only a target has it, the master (its runner
  drives the target over SSH); `host:name` -> that node.
- **`friday dispatch <id>`** (new subcommand, deterministic): pick the node; over `ssh`: ensure
  the repo clone exists and is fetched, create a worktree on `friday/<id>` from the directive's
  base, then start `tmux new -d -s <id> 'claude --model opus --remote-control --name <id>@<node> "/friday:execute <id>"'`
  in that worktree (with `FRIDAY_RUNTIME` set). Record the dispatch (node, tmux session, time)
  in the directive's Log and set `Status: dispatched@<node>`. Refuse when the directive is not
  approved or the node is unreachable (`tailscale ping` / `ssh -o ConnectTimeout=5`).
- **Reporting back:** the worker session uses Claude Code cross-session messaging to send the
  master "done <id> PR <url>" or "blocked <id>: <reason>". Verify the tool names and that
  messaging reaches a Remote Control session on another machine before relying on it; the
  fallback is that `friday status` (phase 4) reads directive Status lines from each node.
- **Hardware on targets:** the lease lives on the machine whose session runs the SSH command
  (`~/.local/state/friday/leases/`). One master drives each target, so that is enough for now;
  note it in `docs/fleet.md`.
- **Tests:** unit-test routing and the command lines `dispatch` builds with a fake `ssh` on PATH;
  then one live run: dispatch `bench`-sized directive from the laptop to the workstation.
- **Gate:** a directive dispatched from the laptop runs on the workstation, its PR opens, and the
  master session receives the message, with no manual step on the workstation.

## 6. Phase 4: status page and docs

- `friday status --json` per node (directives with Status, tmux sessions, leases, `runs/*/*.exit`,
  `nvidia-smi` summary where present); `friday status --html` on the master collects every node's
  JSON over SSH into one static page: a "needs you" list first (blocked directives, sessions
  waiting for input, hardware asks, open PRs), then one section per project and per machine.
  Serve with `tailscale serve` (tailnet only). Reads existing state; writes none.
- Docs to add: `docs/fleet.md` (adding a node, tags, Tailscale SSH, dispatch, leases, Remote
  Control), `docs/dashboard.md`.
- Gate: a day of work run from the page and the phone without opening a terminal on a worker.

## 7. Other open items

- LICENSE for friday (ask the user which; `claude plugin validate` warns without one).
- Add `.claude-plugin/marketplace.json` so the plugin installs with `/plugin install` instead of
  `--plugin-dir` (check the current marketplace format in the Claude Code docs first).
- A `sweep` workflow (one agent per config or dataset) with an explicit concurrency limit
  argument, e.g. at most 2 container builds at once on the laptop.
- Parallel directives within a goal: run them as sub-branches merged into the goal branch (follow-up
  to the goal model; today directives in a goal run one at a time). Every run of
  `workflows/execute.js` shows the same name in `/workflows` (`meta.name` must be a literal), so
  when this lands, `log()` the directive id right after the input check and prefix every agent
  label with `[<id>]` so concurrent runs can be told apart.
- fleet-02 amendment: its per-directive worktree and branch (`friday/<id>`) must be changed to the
  goal branch (`friday/<goal>`) before fleet-02 runs.
- Merge `v1` into `main` after phase 3 works; then migrate other v0.20 projects with
  `docs/migrating-from-v0.md`.

## 8. How to continue

```bash
cd ~/Documents/claude_temp/friday            # branch v1
uv run --with pytest pytest -q && claude plugin validate .
claude --model fable --plugin-dir .
```

Then, in that session: "Read docs/HANDOFF.md. Do step 0 (check the two open questions in
section 4 with a throwaway directive), then /friday:plan phase 3 from section 5." Directives for
friday itself go in this repo's `docs/directives/` with `Verify: uv run --with pytest pytest -q && claude plugin validate .`.
