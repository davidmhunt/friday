# Guardrails: the four hooks

What the four hook scripts enforce, which adapters they are wired into, and how `command_guard.py` behaves inside Docker. Back to the [User Guide](../USER_GUIDE.md).

Behind the rules in [rules.md](rules.md) sit four small, dependency-free scripts that back
some of them mechanically instead of relying on every role remembering to
self-police. They live once in `.friday/templates/adapters/hooks/`, and both
`.claude/hooks/` and `.agents/hooks/` in this project are symlinks to that
same implementation — editing hook logic anywhere updates both adapters at
once, because there's only one copy.

| Hook | Rule it backs | Posture |
|------|---------------|---------|
| `check_agent_spawn.py` | Spawn titles ([User Guide, Roles and tiers](../USER_GUIDE.md#roles-and-tiers)) | **Blocks** a malformed `role(model): task` spawn title; warns on an un-escalated `[heavy]` spawn |
| `command_guard.py` | Command execution policy | **Allow / Force-Ask / Deny** on commands, by pattern |
| `check_md_hygiene.py` | Rule 8 | **Warn-only** |
| `check_commit_msg.py` | Rule 12 (work-record attribution) | **Warn-only** |

Two postures, and don't confuse them:

> [!WARNING]
> `check_agent_spawn.py` genuinely **blocks** a malformed spawn — that one
> can stop a session in its tracks until the title is fixed. Everything
> else in this table either just warns, or (for `command_guard.py`) is
> only wired into one adapter. None of the other three will ever refuse a
> commit or a tool call on your behalf.

- **`command_guard.py` is wired for the Antigravity adapter only today**
  (via `.agents/hooks.json`, `PreToolUse` on `run_command`). It is **not**
  wired into the Claude Code adapter — running Claude Code sessions in
  this project get no command-level allow/force-ask/deny enforcement from
  this hook. Don't assume it's protecting a Claude Code session just
  because the file exists in `.claude/hooks/`.
- **`check_md_hygiene.py`** and **`check_commit_msg.py`** are wired as git
  hooks (`pre-commit` and `commit-msg` wrappers) and always exit 0 — a
  violation prints a warning, but the commit still goes through. Nothing
  stops you from committing over-cap files or a badly attributed message;
  the WARN is a nudge to fix it on the next pass, not a gate.
  `check_md_hygiene.py` also warns — rather than silently skipping, as it
  once did — when a `FILE_CAPS` path is configured but
  doesn't exist on disk (`WARN | hygiene | configured path not found:
  <path>`), so a relocated or mistyped path shows up instead of quietly
  going unenforced.
- **`check_commit_msg.py`** carries a second check on top of the
  role-prefix check every commit gets: a commit from any producing role
  (Planner, Coder, Runner, Reviewer, Author, Researcher, Editor, and every
  project specialist — `Harness:` and `Architect:` are exempt) must name a
  directive (`Directive: <id>` or an inline `directive <id>` mention) and a
  tracker reference (`#123`, `!45`, `ABC-12`, or the literal `no tracker`)
  in its body (git's own trailing `#`-comment block is stripped first).
  This exists because the harness's working state lives in gitignored
  `.friday/active/`, so the commit message is the durable carrier of *why*
  the work happened — see [state_files.md](state_files.md) and
  `.friday/active/harness/rules/version_control.md`. Still warn-only:
  `commit-msg` is symlinked straight into `.git/hooks/commit-msg`, and a
  blocking check here would strand an agent mid-pass with no escape hatch.
- **Project specialists are discovered, not configured.** Both
  `check_agent_spawn.py` and `check_commit_msg.py` list
  `.friday-project/roles/*.md` at run time and treat each role found there
  like a core producing role ([User Guide, Roles and tiers](../USER_GUIDE.md#roles-and-tiers)).

**Running them by hand:**

```bash
python3 .claude/hooks/check_md_hygiene.py       # or .agents/hooks/...
python3 -m pytest .friday/templates/adapters/hooks   # the hooks' unit tests (maintainers)
echo '{"toolCall":{"name":"invoke_subagent","args":{"Subagents":[{"TypeName":"coder","Role":"bad title"}]}}}' \
  | python3 .claude/hooks/check_agent_spawn.py
```

A WARN from any of these means "fix it in your next edit to that file" —
it's advisory, not a stop-work order. If you see a hook firing when it
shouldn't (or silent when it should have fired), see the troubleshooting
table in [troubleshooting.md](troubleshooting.md).

## Container mode: `command_guard.py` behaves differently inside Docker

`command_guard.py` has two modes, and the difference is significant enough
that you should know which one you're in before letting an agent run
unattended.

| | Host | Container |
|---|---|---|
| Deny list | applies | applies |
| Force-ask list | applies | **skipped** |
| Allow list | applies | **skipped** |
| Unrecognized command | force-ask | **allowed** |

Container mode is switched on by `ANTIGRAVITY_CONTAINER=1` or
`CONTAINER_AUTO_ALLOW=1`, both of which `docker/docker-compose.harness.yml`
sets automatically when the Antigravity adapter is enabled — this is the
gitignored, harness-only override ([docker.md](docker.md)), so these variables exist only for
someone who actually has the `.friday/` submodule; a teammate running the
project-owned `docker/docker-compose.yml` alone never sees them. The point
is autonomy: an agent working in a disposable container shouldn't stop
every few minutes for a confirmation you'd grant anyway.

> [!WARNING]
> **The container is isolated from the host, but not sealed off from it.**
> `docker/docker-compose.yml` bind-mounts the project directory at
> `/<project name>`, forwards your host `ssh-agent` socket, and mounts your
> `~/.gitconfig`. So
> a command running unattended in container mode can delete real files in
> your repo and can reach the network with your real git identity. Container
> mode is a reasonable trade for a scratch project; think twice before
> enabling it somewhere the working tree holds uncommitted work you can't
> reproduce.

Because the deny list is the *only* layer left in container mode, it carries
weight it didn't have before, and it is deliberately broader than the
minimum: it blocks `rm -rf` aimed at `..`, a bare `*`, `.`, `~` or an
absolute path; `git push` force-pushes spelled either `--force` or as a
`+refspec`; `git remote add` (the container carries your ssh identity); and
remote-code-execution shapes including `curl … | bash`, the `curl … && sh …`
form that splits across two sub-commands, and `eval "$(curl …)"`.

It cannot catch everything. In particular, a fetch in one tool call and a
`sh /tmp/x.sh` in the *next* one are two separate command lines, and nothing
links them. Container mode assumes the agent is not adversarial — it defends
against plausible mistakes, not against a determined attacker.

**Turning it off.** Delete the two `environment:` entries from
`docker/docker-compose.harness.yml` (not the base `docker-compose.yml` —
they live in the harness override, see [docker.md](docker.md)) and `docker compose up -d`
again. You'll get host behavior — force-ask prompts — inside the
container.

For Antigravity specifically there is a *second*, independent policy layer:
`docker/antigravity_settings.json`, pre-seeded into the image at
`~/.gemini/antigravity-cli/settings.json`. That is the CLI's own permission
system (`permissions.allow` / `.ask` / `.deny`, with `command(...)`,
`read_file(...)`, `write_file(...)`, `read_url(...)` and `mcp(...)` rules),
and it covers things the hook cannot see at all — reading `~/.ssh/**`,
writing `.git/**`, fetching a URL. The two layers are complementary, not
redundant, and neither is a substitute for the other.
