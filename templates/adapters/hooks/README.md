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
| `command_guard.py` | Command execution policy | **Allows** safe/read-only commands (and `git commit` off `main`/`master`), **Forces Ask** on state changes (commit on `main`, push, merge, checkout, rm, unclassified commands, ...), **Denies** destructive actions (sudo, force-push, `rm -rf` of `/ ~ . ..`, `git remote add`, `curl \| sh`, ...) | `.agents/hooks.json` (`PreToolUse` on `run_command`) — Antigravity only; Claude Code uses its own permission settings |
| `check_md_hygiene.py` | markdown hygiene | Warn-only | `pre-commit` wrapper + Controller session start / Reviewer close-out |
| `check_commit_msg.py` | work-record attribution | Warn-only | `commit-msg` wrapper — **git only** |

## Install the git hooks

**Only if this project uses git.** If work is recorded some other way (see
`.friday/active/harness/rules/version_control.md`), delete `check_commit_msg.py`,
`commit-msg`, and `pre-commit`, and run `check_md_hygiene.py` from the
Controller/Reviewer protocols instead.

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

- `check_agent_spawn.py`: Validates subagent spawn calls against the `role(model): task` convention and checks `[heavy]` tier escalation. `HIGH_TIER_KEYWORDS` is read automatically from the consumer project's `harness.config.env` (`HIGH_TIER_MODEL_KEYWORDS`) at hook run time — no manual sync needed. Falls back to `("opus",)` if no config file is found (e.g. before setup has run). **Blocking mechanism:** on Claude Code a violation exits 2 with the reason on stderr (verified live: Claude Code ignores a JSON `deny` from this hook, and only the exit code blocks the spawn); on Antigravity it prints a JSON `{"decision": "deny"}` and exits 0.
- `command_guard.py`: The allow-list's package-manager, test and LaTeX patterns are derived at import time from `harness.config.env` (`PACKAGE_MANAGER*`, `TEST_CMD`, `LATEX_DRAFTING_ENABLED`), falling back to `uv` + LaTeX defaults when absent. **Branch rule:** a plain `git commit` is auto-allowed on any branch except `main`/`master`; it falls back to force-ask when the branch can't be determined (detached HEAD, not a repo), when the line uses `cd`/`git -C`/`--git-dir`/`--work-tree`, or on `main`. Merge, push, checkout, switch, reset etc. always ask. Enforces auto-allow, force-ask, and deny command execution policies (configured with `DENY_PATTERNS`, `FORCE_ASK_PATTERNS`, `ALLOW_COMMAND_PATTERNS`) — its allow-list currently assumes a `uv`/`pytest`/`latexmk`-flavored toolchain; extend the patterns if this project uses a different package manager.
  - **Container mode.** When `ANTIGRAVITY_CONTAINER=1` or `CONTAINER_AUTO_ALLOW=1` is set — this project's `docker-compose.yml` sets both — `evaluate_subcommand` returns `allow` for anything `DENY_PATTERNS` doesn't catch, skipping force-ask and the allow list entirely. `DENY_PATTERNS` is therefore the *only* policy layer inside the container; treat any change to it accordingly. Detection is keyed to those two variables alone and deliberately **not** to `/.dockerenv`, which exists in any container at all (a devcontainer, a CI job, a nested `docker run`) and would silently drop the guard somewhere nobody opted in.
  - **Tests must pin the mode.** Every host-mode assertion in `test_command_guard.py` passes `in_container=False` explicitly rather than relying on ambient detection, so the suite still passes when run inside the container it targets. If you add a test, pin it the same way — the one exception is `test_env_var_activates_container_mode`, which exercises the ambient path on purpose.
- `check_md_hygiene.py`: `FILE_CAPS` and `DIRECTIVE_CAP` (each open
  `plans/directives/*.md`) must match the caps in
  `.friday/active/harness/rules/md_hygiene.md`.
- `check_commit_msg.py`: `CORE_ROLE_PREFIXES` if you renamed any core roles.
- **Project-specific specialists need no configuration here.** Both
  `check_agent_spawn.py` and `check_commit_msg.py` list
  `.friday-project/roles/*.md` in the consumer repo at run time: each role
  found there gets the `role(model): task` title check, a `<role>-heavy`
  escalation variant, and a `<Role>:` commit prefix that requires a
  directive/tracker body. Core role names are never redefined.

Each runs standalone, so you can verify behavior without a live session
(paths below assume the `.claude/` adapter; substitute `.agents/` if
that's the one you're testing):

```bash
python3 .claude/hooks/check_md_hygiene.py
python3 .claude/hooks/test_command_guard.py   # also: test_check_agent_spawn.py, test_check_commit_msg.py, test_check_md_hygiene.py
echo '{"toolCall":{"name":"invoke_subagent","args":{"Subagents":[{"TypeName":"coder","Role":"bad title"}]}}}' \
  | python3 .claude/hooks/check_agent_spawn.py
```
