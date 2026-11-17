# fleet-05: `friday nodes --check` reports blocking prompts; `friday nodes --setup <node>`
Status: approved
Goal: fleet-hardening
Node: any
Deliverable: code
Land: goal
Verify: uv run --with pytest pytest -q tests/test_node_setup.py && uv run --with pytest pytest -q && claude plugin validate .
Hardware: none

## Goal
`friday nodes --check` flags, per master and worker node, each Claude Code first-run prompt that
would stop a dispatched session (workflow approval, auto-mode opt-in), each with a one-line fix,
and `friday nodes --setup <node>` sets the settings that clear them on that node after the user
confirms. docs/fleet.md describes both, plus the master's own ssh setup from the first live run.
tests/test_node_setup.py proves the check and the setup against a fake `ssh`.

## Steps
1. Extend `check_node` (bin/friday, via `friday_fleet.ssh_cmd`): read the node's
   `~/.claude/settings.json` and report `workflow prompt` unless `skipWorkflowUsageWarning` is true,
   and `auto-mode prompt` unless `skipAutoPermissionPrompt` is true; each a FAIL with the fix
   `friday nodes --setup <node>`. A missing or unparsable settings file counts as both prompts.
2. Add `friday nodes --setup <node>`: print the exact keys it will set and the file, ask
   `y/N` on the terminal (refuse without a TTY unless `--yes`), then merge those keys into the
   node's `~/.claude/settings.json` (other keys unchanged, temp file + rename, one backup to
   `settings.json.friday-bak`). It never touches trust, credentials or permission rules.
3. Update docs/fleet.md: the node prompts and `--setup`; master setup learned on the laptop
   (an ssh server or `tailscale set --ssh`; the node's tailnet name, not its hostname; accept the
   host key once; key auth via `ssh-copy-id` so `BatchMode` works); run `friday dispatch` from the
   repo you want dispatched. Add a CHANGELOG entry.
4. Add `tests/test_node_setup.py`: check output with both keys missing, one set, both set, and an
   unparsable file; `--setup` merges and backs up, refuses without a TTY, proceeds with `--yes`,
   and leaves other keys intact; `tests/test_docs.py` still passes with `--setup` documented.

## Out of scope
- Installing or updating Claude Code, tmux, gh or Tailscale on nodes.
- Setting trust (fleet-04) or permission rules on nodes.
- Detecting prompts in an already-running session (status-02's "needs you" list).

## Log
