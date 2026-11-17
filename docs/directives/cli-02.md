# cli-02: Slash commands `/friday:nodes`, `/friday:status`, `/friday:dispatch`, `/friday:clean`
Status: approved
Goal: cli-ergonomics
Node: any
Deliverable: code
Land: goal
Verify: uv run --with pytest pytest -q tests/test_slash_commands.py && uv run --with pytest pytest -q && claude plugin validate .
Hardware: none

## Goal
The friday plugin offers four user-invoked slash commands that run the CLI and report the result
in a few lines: `/friday:status` and `/friday:nodes` (read-only), and `/friday:dispatch <goal>` (passed as `--goal`)
and `/friday:clean <node>`, which always run the `--dry-run` form first, show it, and run the real
command only after the user says yes in the session. They work from any session that loads the
plugin, including over Remote Control. tests/test_slash_commands.py checks their files and that
each names only real CLI commands.

## Steps
1. Add `skills/status/`, `skills/nodes/`, `skills/dispatch/` and `skills/clean/`, each a
   `SKILL.md` with `name`, a `description` saying it is user-invoked, `argument-hint` where it takes
   an argument, and `disable-model-invocation: true` so Claude does not start them on its own.
   Bodies: run the CLI through `${CLAUDE_PLUGIN_ROOT}/bin/friday` (so PATH does not matter) from
   the repo root, summarise the output (needs-you
   items first), and for dispatch and clean run `--dry-run`, show the plan, ask, and only then run
   the real command; on refusal, show the CLI's one-line fix.
2. README and docs/fleet.md list the slash commands next to the CLI forms; CHANGELOG entry.
3. Add `tests/test_slash_commands.py`: each SKILL.md parses (frontmatter keys present,
   `disable-model-invocation: true`), every `friday …` command named in a body exists in
   `bin/friday`'s parser, and dispatch and clean bodies contain the dry-run-then-ask order;
   `claude plugin validate .` passes in Verify.

## Out of scope
- Slash commands for `start`, `finish`, `land` or `release` (the execute workflow runs those).
- Acting on goals from the dashboard (a later goal).

## Log
