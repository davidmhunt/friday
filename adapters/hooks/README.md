# Mechanical backstops

Dependency-free checkers and security guards behind project policies and
rules. All are advisory except the spawn-title format check and command
permission guard, which gate/block.

These implementations live once, here in `adapters/hooks/` (this repo).
In a consumer project both `.claude/hooks/*` and `.agents/hooks/*` are
symlinks to these same files, so editing hook logic here updates both
adapters simultaneously — there is exactly one implementation to maintain,
not two that can drift apart.

| File | Rule | Posture | Wired up by |
|------|------|---------|-------------|
| `check_agent_spawn.py` | Dispatch / spawn titles | **Blocks** a malformed role-spawn title; warns on an un-escalated `[heavy]` spawn | `.claude/settings.json` (`PreToolUse` on `Agent`/`Task`) and `.agents/hooks.json` (`PreToolUse` on `invoke_subagent`) |
| `command_guard.py` | Command execution policy | **Allows** safe/read-only commands, **Prompts/Forces Ask** on state changes/modifications, **Denies** destructive actions | `.agents/hooks.json` (`PreToolUse` on `run_command`) |
| `check_md_hygiene.py` | markdown hygiene | Warn-only | `pre-commit` wrapper + Planner/Reviewer pass start |
| `check_commit_msg.py` | work-record attribution | Warn-only | `commit-msg` wrapper — **git only** |

## Install the git hooks

**Only if this project uses git.** If work is recorded some other way (see
`harness/rules/version_control.md`), delete `check_commit_msg.py`,
`commit-msg`, and `pre-commit`, and run `check_md_hygiene.py` from the
Planner/Reviewer pass protocols instead.

`init_harness.py` installs these automatically, anchored consistently at
`.claude/hooks/` (which is itself a symlink into this directory) — this is
the one canonical anchor; don't also anchor `.git/hooks/` at `.agents/hooks/`,
or the two can drift out of sync with whichever the docs describe. To do it
by hand from the repo root:

```bash
ln -sf ../../.claude/hooks/pre-commit  .git/hooks/pre-commit
ln -sf ../../.claude/hooks/commit-msg  .git/hooks/commit-msg
```

Both wrappers always exit 0 — a violation prints, it never blocks a commit.

## Configure before relying on them

- `check_agent_spawn.py`: Validates subagent spawn calls against the `role(model): task` convention and checks `[heavy]` tier escalation. `HIGH_TIER_KEYWORDS` should match `harness.config.env`'s `HIGH_TIER_MODEL_KEYWORDS`.
- `command_guard.py`: Enforces auto-allow, force-ask, and deny command execution policies (configured with `DENY_PATTERNS`, `FORCE_ASK_PATTERNS`, `ALLOW_COMMAND_PATTERNS`) — its allow-list currently assumes a `uv`/`pytest`/`latexmk`-flavored toolchain; extend the patterns if this project uses a different package manager.
- `check_md_hygiene.py`: `FILE_CAPS` must match the caps in
  `harness/rules/md_hygiene.md`.
- `check_commit_msg.py`: `ROLE_PREFIX_RE` if you renamed any roles.

Each runs standalone, so you can verify behavior without a live session
(paths below assume the `.claude/` adapter; substitute `.agents/` if
that's the one you're testing):

```bash
python3 .claude/hooks/check_md_hygiene.py
python3 .claude/hooks/test_command_guard.py
echo '{"toolCall":{"name":"invoke_subagent","args":{"Subagents":[{"TypeName":"coder","Role":"bad title"}]}}}' \
  | python3 .claude/hooks/check_agent_spawn.py
```
