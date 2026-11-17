# fleet-03: Fleet docs and planning hand-off
Status: approved
Node: any
Verify: uv run --with pytest pytest -q tests/test_docs.py && uv run --with pytest pytest -q && claude plugin validate .
Hardware: none

## Goal
A reader can add a node and dispatch to it from docs/fleet.md alone, and `/friday:plan` offers
`friday dispatch` for directives whose `Node:` this machine doesn't satisfy. This directive is
also the phase 3 live gate: it is dispatched from the laptop to Alfred.

## Steps
1. Write `docs/fleet.md`: where the registry lives (lookup order `$FRIDAY_NODES`, the friday
   folder's gitignored `nodes.toml`, `~/.config/friday/nodes.toml`; copy `nodes.example.toml`), and
   that an installed (cached) plugin copy won't see the clone's `nodes.toml`, so use `--plugin-dir`
   on the clone or set `FRIDAY_NODES`; where work happens on a node and how to change it (`repos`;
   existing clone `<repos>/<repo>` reused, worktrees at `<repos>/<repo>.friday/<id>` on
   `friday/<id>`, your checkout untouched); why remote commands prepend `$HOME/.local/bin` to PATH
   (non-interactive ssh skips `.zshrc`); the nodes.toml format (every key fleet-01 accepts, with the laptop /
   alfred / ground-bot example; Alfred's ssh is `david@alfred-ts`); routing rules; one-time node
   setup (Tailscale SSH, `claude` signed in and current, `gh auth login`, tmux, the friday clone at
   `plugin_dir`, trusting `repos` once by running `claude` there); `friday nodes --check`;
   `friday dispatch` and its refusals; the master must run with Remote Control on and a name
   without `@` so workers can message it; where dispatches are recorded; hardware leases live on
   the machine that runs the SSH command, one master per target; the fallback when no message
   arrives (`tmux attach -t <id>` on the node, or the Remote Control session in the Claude app).
2. Update `skills/plan/SKILL.md` step 4 and `README.md`: a directive whose `Node:` this machine
   doesn't satisfy runs with `friday dispatch <id>`; add `nodes` and `dispatch` to the command list
   in `bin/friday`'s docstring if missing; add a CHANGELOG entry.
3. Add `tests/test_docs.py`: every key `friday_fleet` accepts and every `friday` subcommand
   appears in docs/fleet.md or README.md (so the docs can't silently drift).

## Out of scope
- docs/dashboard.md and the status page (phase 4).
- Marketplace install; LICENSE.

## Log
