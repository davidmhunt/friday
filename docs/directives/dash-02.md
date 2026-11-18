# dash-02: `friday nodes --check` shows each node's dash status; the docs explain registration
Status: done
Goal: deploy
Node: any
Deliverable: code
Land: goal
Verify: uv run --with pytest pytest -q tests/test_nodes_check_dash.py && uv run --with pytest pytest -q && claude plugin validate .
Hardware: none

## Goal
`friday nodes --check` adds one line per node from the dash's `/api/state`: `dash: ok (12 s ago)`,
`stale`, `missing` with the fix (`friday nodes --setup <node>`), or `dash: not running` with
`friday dash up`. A node that never reported shows the same fix on its Machines card on the page.
docs/dashboard.md opens with "How machines and projects get on the page": machines are the
registry's nodes, a node appears once its timer pushes, and projects are the friday repos under
that node's `repos` folder. tests/test_nodes_check_dash.py proves each line.

## Steps
1. `bin/friday` `--check`: fetch `<master url>/api/state` (2 s timeout, localhost first on the
   master), map each node's status to one line with its fix; an unreachable dash is one line, not
   an error exit for the other checks.
2. dash/static/app.js: a `missing` machine card shows "never reported: run
   `friday nodes --setup <name>` on the master"; a `stale` card shows its last-seen age.
3. docs/dashboard.md: the registration section (registry, node.toml from node-01, push timer,
   repos folder, a friday repo = a git repo with docs/goals or docs/directives), with the
   three-command path for a new machine: add it to nodes.toml, `friday nodes --setup <name>`,
   open the page.
4. tests/test_nodes_check_dash.py: ok, stale, missing and not-running lines against a fake
   state server; check still runs the other items when the dash is down; the missing-card text is
   in app.js.

## Out of scope
- A separate `friday doctor` command (folded into `--check` here).
- Acting on goals or nodes from the page.

## Log

### 2026-11-17
Commits:
- f557f40 dash-02: test that the missing-card text ships in the page JS
- 679247f dash-02: docs/dashboard.md opens with how machines and projects get on the page
- 435291b dash-02: a missing machine card says to run friday nodes --setup <name> on the master
- ce265a1 dash-02: friday nodes --check prints each node's dash status line with its fix
Verify: Verify passed: uv run --with pytest pytest -q tests/test_nodes_check_dash.py && uv run --with pytest pytest -q && claude plugin validate .
Independent review: no gaps
