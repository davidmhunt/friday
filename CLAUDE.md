# friday (the plugin's own repo)

friday is a Claude Code plugin: a CLI (`bin/friday`, `lib/friday_core.py`), hooks, skills,
agents and a dashboard (`dash/`). The single reference for what it does is `docs/spec.md`.

## Where things are
- `docs/spec.md`: the spec (model, file formats, lifecycle, commands, hooks, config, limits).
  Start there. `docs/workflow.md` is the walkthrough, `docs/fleet.md` covers nodes.
- `lib/friday_core.py`: parser, header fields, statuses, exit codes, deny list.
- `hooks/`, `skills/`, `agents/`, `workflows/`: the plugin's parts.
- `docs/directives/<id>.md`: directives for friday's own development.

## Running the tests
- Whole suite: `uv run --with pytest pytest -q`
- Docs and spec only: `uv run --with pytest pytest -q tests/test_docs.py tests/test_spec.py`
- Plugin manifest: `claude plugin validate .`
- `tests/test_spec.py` fails when docs/spec.md and the code disagree (commands, flags,
  header keys, statuses, exit codes, deny-list rules). Change both together.

## Default Verify
A directive here normally uses:
`uv run --with pytest pytest -q tests/test_docs.py tests/test_spec.py && uv run --with pytest pytest -q && claude plugin validate .`
Narrow it to the tests that prove the directive when the full run is not needed.

## Do not edit the live plugin checkout
The checkout loaded as the plugin (`claude --plugin-dir ...` or the installed copy) is
running code: hooks and the CLI execute from it. Never edit files there while a session uses
it. Work in a worktree on a `friday/<goal>` branch (`friday start <id>` sets this up) and
reload the plugin after merging.

## Rules of the repo
- One commit per step, only if tracked files changed; the last line is `Directive: <id>`.
- Do not edit a directive's `Status:` or `## Log` by hand; `friday start` and `friday finish`
  write them.
- Never weaken or skip a test to get green.
- Keep other docs linking to the spec rather than repeating it.
