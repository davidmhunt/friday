# friday

A Claude Code plugin for research repos: you plan a goal with the model, approve it once, and
friday executes it behind deterministic gates. Each unit of work is a **directive** with a
`Verify:` command; it is done only when that command passes and an independent reviewer agrees.
Hooks enforce what must never bend: a command deny list, running code through `./run`, hardware
behind a prompt and a lease, and commits that name their directive.

v1 replaces the v0.20 multi-role harness (tag `v0.20.0`), which was built for a mid-tier
orchestrator. With Fable or Opus as the session model, friday keeps only the parts that check and
constrain the work.

## Install

```bash
git clone https://github.com/davidmhunt/friday ~/src/friday     # branch v1
claude --plugin-dir ~/src/friday                                 # try it in one session
```

To keep it enabled, add `~/src/friday` as a local marketplace with `/plugin` and install it from
there. Requires Claude Code with workflows (v2.1.154+) and `python3` on the host.

## Use

```text
/friday:plan add range-limit checks for chirp configs     # interview, then directives in docs/directives/
(approve)                                                  # the only planned stop
/friday:execute core-03                                    # implement, verify, review, push, PR
```

Then review the PR. `friday status` in a shell (or ask Claude to run it) lists directives, the one
active in this worktree, and hardware leases. See [docs/workflow.md](docs/workflow.md).

## What's in it

| Part | What it does |
|---|---|
| `skills/plan` | Interviews you, writes directives with an executable `Verify:`, asks for approval |
| `workflows/execute.js` | Prepare → implement each step → Verify (fix loop) → Opus review → land |
| `agents/` | `implementer` (Sonnet; Opus for `[heavy]` steps), `verifier` (Opus, read-only), `runner` (Haiku, long and remote runs) |
| `hooks/` | Deny list, `./run` enforcement, hardware prompt + lease, commit trailer, Verify gate on Stop |
| `skills/` | `directive` (format), `hardware`, `long-jobs`, `data-artifacts` |
| `bin/friday` | `status`, `new`, `start`, `verify`, `finish`, `release` |

## Per project

A project adds three things (CPSL_TI_Radar is the worked example):

- `CLAUDE.md`: facts the model can't infer from the code, under about 60 lines.
- `.claude/friday.json`: the run wrapper, which tools must go through it, and hardware patterns.
- `docs/directives/`: one file per directive.

Optionally a `./run` wrapper and dev container ([docs/runtime.md](docs/runtime.md)) and project
skills under `.claude/skills/`.

## Status

v1 is in alpha. Next: fleet dispatch across machines over Tailscale, and a status page
([design spec](docs/workflow.md#roadmap)). Migrating a v0.20 project:
[docs/migrating-from-v0.md](docs/migrating-from-v0.md).

## Tests

```bash
uv run --with pytest pytest tests/ -q
claude plugin validate .
```
