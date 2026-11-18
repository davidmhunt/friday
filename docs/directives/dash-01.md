# dash-01: `friday dash` runs as a Docker Compose service on the master
Status: approved
Goal: deploy
Node: any
Deliverable: code
Land: goal
Verify: uv run --with pytest pytest -q tests/test_dash_docker.py && uv run --with pytest pytest -q && docker compose -f deploy/compose.yaml config -q && docker build -q -f deploy/Dockerfile . && claude plugin validate .
Hardware: none

## Goal
`friday dash up` starts the dashboard as a Docker Compose service on the master
(`deploy/compose.yaml`, `deploy/Dockerfile`), restarting with the machine, and `friday dash down`
stops it; plain `friday dash` still runs it in the foreground. In the container the dash only
receives reports, so the master pushes its own snapshot with its push timer like every other node.
tests/test_dash_docker.py proves the compose file and the up/down commands are what this
directive says; Verify also builds the image.

## Steps
1. [heavy] deploy/Dockerfile: python:3.12-slim with the plugin's `bin/`, `lib/` and `dash/`, plus
   the `tailscale` and `gh` CLIs (official apt repos, pinned by release). Runs
   `friday dash --no-self` as a non-root user.
   Heavy because: the container must keep the dash's security rules (whois sender check, bind
   only to 127.0.0.1 and the tailnet IP) while running outside the host's process space.
2. deploy/compose.yaml, service `friday-dash`: `network_mode: host` (so it binds the tailnet IP
   and sees real peer addresses), `restart: unless-stopped`, read-only mounts of the registry
   (`~/.config/friday/nodes.toml`) and `/var/run/tailscale/tailscaled.sock`, a named volume for
   the dash state dir, and `GH_TOKEN` taken from the environment (no token in any file).
3. lib/friday_dash.py: `--no-self` skips `refresh_master`; a localhost report is still accepted
   as the master's. `bin/friday`: `friday dash up` runs `docker compose -f <plugin>/deploy/compose.yaml
   up -d --build` with `GH_TOKEN` from `gh auth token` (left unset, with a note, when gh is signed
   out); `friday dash down` runs `... down`; both say what they ran and fail clearly when docker
   is missing.
4. tests/test_dash_docker.py: parse compose.yaml (host network, both read-only mounts, volume,
   restart, no secret values); `up`/`down` build the right argv against a fake `docker` and
   `gh` and keep the token out of argv; `--no-self` never calls collect; a localhost report still
   lands as the master.
5. docs/dashboard.md: "Running it in Docker" (up, down, logs, the master's push timer via
   `friday nodes --setup laptop`), and that the foreground `friday dash` still works.

## Out of scope
- Running workers' sessions or the push timer in containers.
- Any registry, image or compose publishing (no registry push, no CI).
- TLS or a reverse proxy; the tailnet is the security boundary.

## Log
