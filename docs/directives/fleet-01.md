# fleet-01: Node registry and routing (`friday nodes`)
Status: done
Goal: fleet
Node: any
Deliverable: code
Land: pr
Verify: uv run --with pytest pytest -q tests/test_fleet.py && uv run --with pytest pytest -q && claude plugin validate .
Hardware: none

## Goal
friday can read the master's node registry and decide, deterministically, which node runs a
directive from its `Node:` line. `friday nodes` lists the registry and, with `--check`, reports
each node's reachability and readiness. tests/test_fleet.py proves the routing rules and the
probe against a fake `ssh`.

## Steps
1. Add `lib/friday_fleet.py`: `find_nodes_file()` returns the first that exists of
   `$FRIDAY_NODES`, `<friday plugin root>/nodes.toml`, `~/.config/friday/nodes.toml`;
   `load_nodes(path)` reads it as TOML (stdlib `tomllib`). Top-level `report_to` (optional, the master
   session name workers message) and `[node.<name>]` tables with `role` (master|worker|target),
   `ssh`, `runtime` (container|native), `tags` (list), `repos` (dir, `~` allowed), `plugin_dir`
   (friday clone on that node), `launcher` (default `tmux`; only `tmux` accepted for now). Reject
   unknown roles/runtimes/launchers and duplicate or missing `ssh` with a message naming the node
   and key. Workers and the master need `repos` and `plugin_dir`; targets don't.
2. In the same module, `route(node_line, nodes, load)` -> `(node_name, reason)`, where `load` maps
   node name -> running directive count: `any` -> the worker with the lowest load (ties: registry
   order); `tag:x` -> a worker or the master with tag x (lowest load), else the master when only a
   target has x (reason says the master's runner drives that target over SSH); `host:name` -> that
   node (error if it is a target). Raise `RouteError` with a clear message when nothing fits.
3. Add `friday_fleet.ssh_cmd(node, script)`: the argv for one remote call,
   `[$FRIDAY_SSH or "ssh", "-o", "ConnectTimeout=5", "-o", "BatchMode=yes", node.ssh, "bash", "-s"]`
   with the script on stdin. Every remote script starts with `export PATH="$HOME/.local/bin:$PATH"`
   (non-interactive ssh on the workstation does not have it, so `claude` and `uv` are missing).
4. Add `nodes.example.toml` at the repo root (committed: master `laptop`, worker `alfred` with
   `ssh = "david@alfred-ts"` and `repos = "~/Documents"`, target `ground-bot`, every key with a
   comment) and add `nodes.toml` to `.gitignore` (the repo is public; the real registry holds
   tailnet names). Add `friday nodes [--check]` to `bin/friday`. Its first line says which file
   was loaded; with none found it says where to copy the example. Without `--check`, print one
   line per node (name, role, ssh, runtime, tags, repos). With `--check`, run one probe script per node: reachable,
   `claude --version`, `tmux`/`git` present, `plugin_dir` is a git clone, and whether `repos` or a
   parent is trusted in that node's `~/.claude.json` (`projects[<path>].hasTrustDialogAccepted`;
   trust is inherited from parent directories). Print a fix line for each failure, e.g. "run
   `claude` once in ~/src on alfred and accept the trust prompt". Exit 0 only if every worker and
   the master pass. Targets are checked for reachability only.
5. Add `tests/test_fleet.py`: the lookup order; `nodes.example.toml` parses and validates;
   `nodes.toml` is gitignored; registry parsing and validation errors; every routing rule above,
   including load tie-breaks and the target-only tag case; `friday nodes --check` with a fake
   `ssh` script on `$FRIDAY_SSH` that records its argv and stdin and returns canned output (one
   ready node, one unreachable, one untrusted).

## Out of scope
- Dispatching or starting anything on a node (fleet-02).
- herdr as a launcher (the `launcher` key exists so it can be added later).
- Writing to any node's `~/.claude.json`; friday only reads trust.
- `friday status` across nodes (phase 4).

## Log

### 2026-11-17

Commits:
- 0bb8832 Test friday nodes --check with ready, unreachable and untrusted nodes in one run
- dc065f9 Add friday nodes [--check], nodes.example.toml, gitignore nodes.toml
- bb724ad Add friday_fleet.ssh_cmd: argv and PATH-prefixed stdin for one remote call
- e5f6265 Add friday_fleet.route: any/tag/host routing with RouteError
- 2204665 Add node registry loader (friday_fleet) with validation
- 1cd43d6 Start fleet-01

Verify passed: uv run --with pytest pytest -q tests/test_fleet.py && uv run --with pytest pytest -q && claude plugin validate .

Independent review: no gaps
