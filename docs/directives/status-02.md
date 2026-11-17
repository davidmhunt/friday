# status-02: `friday dash` collects node reports pushed over the tailnet, read-only API
Status: approved
Goal: status-page
Node: any
Deliverable: code
Land: goal
Verify: uv run --with pytest pytest -q tests/test_dash_server.py && uv run --with pytest pytest -q && claude plugin validate .
Hardware: none

## Goal
On the master, `friday dash` runs a small stdlib HTTP server bound to localhost and the master's
tailnet address only. Nodes push their `friday status --json` snapshot to it every 30 s
(`friday status --push`, run by a systemd user timer that `friday nodes --setup` installs), and it
accepts a report only from a tailnet peer whose identity (`tailscale whois`) maps to a node in the
registry. It serves the merged state read-only (`GET /api/state`, `GET /api/health`), with
per-node "last seen", stale and missing flags, the master's own snapshot taken locally, and open
`friday/*` PRs from `gh`. tests/test_dash_server.py proves acceptance, rejection and the API.

## Steps
1. [heavy] Server in `lib/friday_dash.py` (stdlib `http.server`, threaded): bind `127.0.0.1` and
   the address from `tailscale ip -4` (refuse to start if `--bind` names anything else, and never
   `0.0.0.0`); port from the registry `[dash] port` (default 8787). Routes: `POST /api/report`,
   `GET /api/state`, `GET /api/health`, and static files for status-03. Heavy because: it is the
   first network listener friday runs, so the bind and sender checks must be right.
2. Sender check for `POST /api/report`: the peer address must be a tailnet address; resolve it with
   `tailscale whois --json <ip>` (cached 5 min); the device's name must match a registry node
   (its `ssh` host or a new optional `tailnet` key) and the JSON's `node` must equal that node;
   body at most 1 MiB and must parse as schema 1. Otherwise 403 or 400, logged one line each.
   Localhost POSTs are accepted only for the master node.
3. State: keep the latest report per node in memory and in `~/.local/state/friday/dash/<node>.json`
   (atomic write) so a restart shows the last known state; mark a node stale after 90 s and missing
   when it has never reported. The master's snapshot is taken in-process every 30 s. Open PRs from
   `gh pr list --json` for each known repo, every 2 min, skipped with a note when gh is unavailable.
4. Node side: `friday status --push [--to <url>]` posts the snapshot (URL from the registry's
   master node and `[dash] port`). `friday nodes --setup <node>` (fleet-05) additionally installs
   and enables a systemd user timer `friday-push.timer` (30 s) on that node after the same y/N
   confirmation; the unit files live in `deploy/`.
5. Write docs/dashboard.md: how it works (push, tailnet-only bind, whois check), starting
   `friday dash` (and a systemd user unit for it), setting up nodes, what stale/missing mean,
   troubleshooting (`friday status --push` by hand). CHANGELOG entry; README mentions it.
6. Add `tests/test_dash_server.py` with a fake `tailscale` on PATH: an accepted report from a
   registry node; rejections for an unknown device, a name/`node` mismatch, oversize and invalid
   bodies, and a non-tailnet peer; refusal to bind `0.0.0.0`; stale and missing flags with a
   controllable clock; state survives a restart; `/api/state` merges the master's own snapshot and
   fake `gh` PRs; the push client posts to the registry URL; `tests/test_docs.py` still passes.

## Out of scope
- The UI (status-03); any action endpoint or write to a repo or node beyond the push timer setup.
- Auth beyond the tailnet identity check; `tailscale funnel` or any public exposure.
- SSH pull of node state (kept only for `--setup`).

## Log
