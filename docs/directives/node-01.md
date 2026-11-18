# node-01: `--setup` writes the node's identity file; `friday status --push` uses it with no registry
Status: done
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

### 2026-11-17
Commits:
- baa4f9f node-01: registry-precedence test uses a valid registry; setup test checks dash port and tailnet
- e302c72 node-01: docs for node.toml and that --setup writes it
- f859e19 node-01: tests for push via the node file's dash URL and status with a bad node file
- 20f9d56 node-01: --setup writes node.toml on the node and lists it in the y/N summary
- 304b446 node-01: status uses the node file when no registry entry matches; push falls back to its dash URL
- b1583b1 node-01: NODE_FILE and load_node_file() read the node identity file
Verify: Verify passed: uv run --with pytest pytest -q tests/test_node_identity.py && uv run --with pytest pytest -q && claude plugin validate .
Independent review: gaps fixed in second review: 1. tests/test_node_identity.py:43-50 (test_registry_beats_node_file): This test does not check the claim in its name, which Step 4 requires ('the registry wins over the node file'). Its registry uses '[nodes.m]', but the loader only accepts '[node.<name>]' tables, so the registry fails to load and the node file is used. The test still passes only because it also passes node_name='regname', and the --node flag wins whatever the registry and file say. If the registry-precedence code were removed, this test would still pass. (evidence: With this test's inputs, collect(..., node_name='regname') returns node=regname with errors=[{'where':'registry','error':'.../nodes.toml: no [node.<name>] tables'}]. Without node_name it returns node=fromfile. lib/friday_fleet.py:122-124 reads data.get('node') and raises 'no [node.<name>] tables'. The code itself is right: a valid '[node.m]' registry whose ssh equals the hostname gives node=m over the node file. Only the test is empty.) 2. tests/test_node_identity.py:53-75 (test_setup_writes_node_file): Step 4 asks for a test of the URL built 'from the master's 'tailnet' or ssh host and '[dash] port''. The test checks only the prefix 'dash = 'http://mhost:'. It never checks the port and has no case where the master has a 'tailnet' key. A wrong port or ignoring 'tailnet' would not be caught. (evidence: assert 'name = 'w'' in text and 'repos = '~/code'' in text and 'dash = 'http://mhost:' in text. The test registry has no '[dash]' table and no 'tailnet' key.)
