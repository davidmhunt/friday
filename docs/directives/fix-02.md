# fix-02: Every command and flag is real, documented in `--help` and allowed without a prompt
Status: approved
Goal: v1-final
Node: any
Deliverable: code
Land: goal
Verify: uv run --with pytest pytest -q tests/test_cli_surface.py && uv run --with pytest pytest -q && claude plugin validate .
Hardware: none

## Goal
The CLI surface is consistent: `friday --help` lists every subcommand and flag the parser accepts
(a test compares them), the flags the docs name exist, and the friday commands that skills and
dispatched sessions run match the allow rules `friday init` writes.

## Steps
1. `friday status --node NAME` (with `--json`/`--push`): passes the name to `collect`, first in
   the identity order docs/fleet.md already states.
2. `friday nodes --check`: report the number of `friday-*` tmux sessions per node, as
   docs/fleet.md says.
3. Help text (bin/friday docstring): add `init`, `session-end`, `unblock`,
   `dispatch --resume/--unblock`, `status --node`; correct the "on PATH" line to name
   `friday install`.
4. Allow rules (`FRIDAY_ALLOW` in lib/friday_core.py, .claude/settings.json): add `friday init`
   and `friday session-end`. Never add `friday accept`. The status, nodes, dispatch and clean
   skills call plain `friday ...` so the rules match, and say to run `friday install` if it is
   not on PATH.
5. Registry: add the `tailnet` key to nodes.example.toml and the key table in docs/fleet.md.
   `friday dash up` mounts the registry file the CLI actually resolved (plugin root or
   `~/.config/friday/nodes.toml`) and fails clearly when there is none.
6. tests/test_cli_surface.py: every parser subcommand and option string appears in the help text;
   every `friday <sub>` in skills/ and workflows/execute.js matches an allow rule, except
   `friday dispatch --goal <g>`, `friday nodes --clean <node>` and `friday release <resource>`,
   which stay prompted on purpose (they act on other machines or free hardware; amended by the
   user 2026-11-18) and are named in the test's `prompted()` list; steps 1, 2, 5.
   CHANGELOG entries.
7. Shell-safe tmux targets: every tmux target friday prints for a person to copy, or builds
   into a command line, is quoted (`-t '=friday-<g>'`), because zsh expands a bare `=word`; remote
   scripts keep running under `bash -s` and local ones under `sh -c`. A test in
   tests/test_cli_surface.py fails on any unquoted `-t =` in bin/ and lib/, and runs the
   `dispatch --resume` kill line under zsh (skipped when zsh is absent). Amended by the user
   2026-11-18.

## Out of scope
- New commands other than `status --node` (accept, result and unblock belong to other directives).

## Log
