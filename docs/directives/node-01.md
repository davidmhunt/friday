# node-01: `--setup` writes the node's identity file; `friday status --push` uses it with no registry
Status: approved
Goal: deploy
Node: any
Deliverable: code
Land: goal
Verify: uv run --with pytest pytest -q tests/test_node_identity.py && uv run --with pytest pytest -q && claude plugin validate .
Hardware: none

## Goal
`friday nodes --setup <node>` writes `~/.config/friday/node.toml` on the node: its registry
`name`, its `repos` and the dash URL (`fd.master_url` of the master's registry). On a node with
no `nodes.toml`, `friday status` and `friday status --push` read that file for the snapshot's
`node`, the repos to scan and the push URL, so Alfred's report says `alfred` and not its hostname
`cpsl-homebase`, and the dash accepts it. tests/test_node_identity.py proves the file is written,
read, and wins over the hostname.

## Steps
1. lib/friday_fleet.py: `NODE_FILE` (`~/.config/friday/node.toml`, `$FRIDAY_NODE_FILE` overrides)
   and `load_node_file()` returning `(name, repos, dash_url)` or None; a malformed file is a
   `RegistryError` naming the file. Keys: `name`, `repos`, `dash`; unknown keys are an error.
2. lib/friday_status.py `registry_node` / `collect`: when no registry entry matches, use the node
   file (name, and `repos` for `find_repos`). Order: `--node` flag, registry match, node file,
   hostname. `bin/friday cmd_status_push`: URL order `--to`, registry master, node file `dash`.
3. `bin/friday` `--setup`: after the settings step, write node.toml on the node over
   `ff.ssh_cmd` (temp file + rename, python3 as the timer step does), and list it in the y/N
   summary. A setup on the master writes one too (harmless; its registry still wins).
4. tests/test_node_identity.py: setup script content for a worker (name, repos, URL from the
   master's `tailnet` or ssh host and `[dash] port`); `collect` with only a node file reports that
   name and scans its repos; the registry wins over the node file; `--push` with no registry uses
   the file's URL; a bad file gives a clear error and status still prints (error in `errors`).
5. docs/fleet.md and docs/dashboard.md: what node.toml holds and that `--setup` writes it.

## Out of scope
- Copying the whole registry to nodes, or nodes dispatching.
- Changing the dash's whois check (it already maps Alfred's device to `alfred`).

## Log
