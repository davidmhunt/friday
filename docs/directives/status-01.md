# status-01: `friday status --json` reports one node's health, GPU, friday work and sessions
Status: done
Goal: status-page
Node: any
Deliverable: code
Land: goal
Verify: uv run --with pytest pytest -q tests/test_status_json.py && uv run --with pytest pytest -q && claude plugin validate .
Hardware: none

## Goal
`friday status --json` prints one JSON snapshot of this node, the payload status-02 receives:
health (uptime, load, RAM, disk), GPUs where `nvidia-smi` exists, every friday repo and goal
worktree under its `repos` with goals and directive statuses, hardware leases, recent
`runs/*/*.exit` results, and each running `friday-*` session with its goal, directive, workflow
phase and step, a "waiting for input" flag and a redacted pane snippet. It writes nothing.
tests/test_status_json.py proves the schema and each field on a fixture tree.

## Steps
1. [heavy] Define the schema in `lib/friday_status.py` (`"schema": 1`): `node`, `host`, `time`;
   `health` (uptime_s, load[3], mem total/used, disk total/used for `repos`); `gpus[]` (name,
   util %, mem used/total, processes); `repos[]` (path, origin, branch, goals[] with status and
   directives[] with id, status, deliverable, title); `leases[]`; `runs[]` (repo, id, name, exit,
   mtime; last 10 per repo); `sessions[]` (tmux name, created, cwd, goal, directive, phase, step,
   `waiting` + matched line, `snippet`). Heavy because: the schema is the contract status-02 and
   status-03 build on, and "waiting" and step detection must hold on the prompts seen so far.
   Waiting: the pane's last lines match a known prompt (folder trust, "Run a dynamic workflow?",
   a permission prompt, "Enter to confirm"); list patterns in one place. Phase/step: from the
   friday marker in the session's cwd plus the workflow status line (`execute … 3/4`) in the pane.
2. Snippet: the last 12 non-blank pane lines, each cut to 200 characters, with redaction applied
   before anything leaves the function: tokens and keys (`sk-…`, `ghp_…`, `gho_…`, `AKIA…`,
   `-----BEGIN … KEY-----` blocks, `Authorization:`/`password=`/`token=` values) become `[redacted]`;
   patterns live in one list with tests.
3. Health and GPU from `/proc/uptime`, `/proc/loadavg`, `/proc/meminfo`, `shutil.disk_usage`, and
   `nvidia-smi --query-gpu=... --format=csv,noheader,nounits` plus `--query-compute-apps`. Every
   external command (tmux, nvidia-smi, git) has a 3 s timeout and is optional: missing means
   empty or null. Repos: this node's `repos` from the registry when present, else the current
   repo; a repo is a git checkout with `docs/goals/` or `docs/directives/`, plus its
   `<repo>.friday/<goal>` worktrees. Parse errors become `errors[]` entries, never a crash.
4. Wire `--json` into `cmd_status`; plain `friday status` output unchanged.
5. Add `tests/test_status_json.py`: a fixture tree (two repos, one goal worktree), fake `tmux`
   (a session waiting at the workflow prompt, a busy one at `execute 3/4`, tmux absent), fake
   `nvidia-smi` (two GPUs, absent), fake `/proc` via a root override; leases and `.exit` files; a
   broken directive gives an `errors[]` entry; every redaction pattern is removed from snippets;
   output matches the schema; plain `friday status` unchanged.

## Out of scope
- Sending the snapshot anywhere (status-02) and showing it (status-03).
- Claude sessions not started by friday (interactive sessions); Windows and macOS nodes.
- Writing any state or acting on what it finds.

## Log

### 2026-11-17
Commits:
- 2afb836 status-01: report registry node name; do not create lease dir on status --json
- 903ac91 status-01 step 5: tests for friday status --json on a fixture tree
- edd67e2 status-01 step 4: friday status --json prints the node snapshot
- f557162 status-01 step 3: health, GPU, repos, runs and session collectors
- 4ede819 status-01 step 2: redacted pane snippet
- de9c31c status-01 step 1: snapshot schema, waiting and workflow-step detection
Notes:
2026-11-17: Dispatched from thinkpadP15v3 to cpsl-homebase
Verify: Verify passed: uv run --with pytest pytest -q tests/test_status_json.py && uv run --with pytest pytest -q && claude plugin validate .
Independent review: gaps fixed in second review: 1. lib/friday_status.py:507 (collect) with bin/friday:59 (cmd_status) and lib/friday_status.py:388-389 (find_repos): 'node' is always the hostname when run from the CLI. The module docstring (line 7) promises the registry node name, but cmd_status calls fs.collect() with no node_name, so collect falls back to 'node_name or host'. find_repos does find the registry node (matching on name or ssh), but its name is never passed back to the snapshot. So a node registered as 'gpu1' with 'ssh = <hostname>' reports 'node: <hostname>'. status-02 builds on this schema and will receive the wrong identity. (evidence: 'snap = empty_snapshot(node_name or host, host, ...)', and cmd_status does 'print(json.dumps(fs.collect(), indent=2))'. Running ./bin/friday status --json here printed node == host == cpsl-homebase. The only test that checks node passes node_name='n1' explicitly (test_schema_and_repos). The CLI test never asserts node.) 2. lib/friday_status.py:519 (fc.list_leases -> friday_core.lease_dir mkdir): The directive says 'friday status --json' 'writes nothing', but it creates ''XDG_STATE_HOME/friday/leases' when that directory is missing, because friday_core.lease_dir() calls mkdir(parents=True). It is minor (an empty directory, made by an existing helper), but it breaks the stated read-only guarantee. The test only checks 'git status --porcelain' in the repo, so it cannot catch this. (evidence: With an empty XDG_STATE_HOME in the scratchpad, 'XDG_STATE_HOME='S ./bin/friday status --json' left ''S/friday/leases' behind (seen with find).)
