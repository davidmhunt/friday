# Dashboard (`friday dash`)

`friday dash` runs on the master and collects a status snapshot from every node in the registry
([fleet.md](fleet.md)). It is read-only: it serves state, it never acts on a repo or a node.

## How machines and projects get on the page

- **Machines are the registry's nodes.** Every `[node.<name>]` in `nodes.toml` ([fleet.md](fleet.md))
  is a machine card on the page. A node in the registry that has not reported shows as missing, with
  the fix on its card.
- **A node appears once its timer pushes.** `friday nodes --setup <name>` writes
  `~/.config/friday/node.toml` on the node (`name`, `repos`, `dash` URL, taken from the registry and
  the master's `[dash] port`) and installs `friday-push.timer`, which runs `friday status --push`
  every 30 s. The first accepted push turns the card from missing to ok.
- **Projects are the friday repos under the node's `repos` folder.** The `repos` key of the node
  (and its `<repo>.friday/<goal>` worktrees) is scanned on every push. A friday repo is a git repo
  with `docs/goals` or `docs/directives`; other folders there are ignored.
- **`friday nodes --check`** prints one `dash:` line per node (ok, stale, missing or not running)
  with its fix.

Adding a new machine takes three commands:

1. Add it to `nodes.toml` on the master: a `[node.<name>]` block with `role`, `ssh`, `repos` and
   `plugin_dir` (see `nodes.example.toml`).
2. `friday nodes --setup <name>` on the master: confirm with y, and it sets up the node and its push
   timer.
3. Open the page (`http://<master tailnet name>:8787`). The machine shows within about 30 s; if it
   does not, run `friday nodes --check`.

## How it works

- **Push.** Each node runs `friday status --push` every 30 s (a systemd user timer) and POSTs its
  `friday status --json` snapshot to `http://<master>:<port>/api/report`. The master takes its own
  snapshot in-process every 30 s. Nothing is pulled over SSH.
- **Tailnet-only bind.** The server listens on `127.0.0.1` and on the address `tailscale ip -4`
  prints, and nowhere else. It never binds `0.0.0.0` or `::`; `--bind ADDR` may only name one of
  those two addresses, anything else is refused at start. Port: `[dash] port` in `nodes.toml`
  (default 8787). It is not exposed with `tailscale funnel` or any other public route.
- **Whois check.** A report is accepted only from a tailnet peer address. The server resolves it
  with `tailscale whois --json <ip>` (cached 5 min); the device name must match a registry node
  (the host in its `ssh`, or its optional `tailnet` key), and the `node` field in the JSON must be
  that same node. The body is at most 1 MiB and must be schema 1. Otherwise the answer is 403 or
  400, and one line is logged. A POST from localhost is accepted only for the master node.
- **State.** The latest report per node is kept in memory and in
  `~/.local/state/friday/dash/<node>.json`, so a restart shows the last known state. Open
  `friday/*` PRs of the repos nodes reported come from `gh pr list --json` every 2 min (skipped,
  with a note in the state, when `gh` is missing or signed out).
- **API.** `GET /api/state` (merged state: nodes, master snapshot, PRs) and `GET /api/health`.
  Static files in the dash's static folder are served for the status page.

## Starting it

On the master:

```
friday dash                 # foreground; Ctrl-C stops it
friday dash --bind 127.0.0.1   # localhost only
```

Without a tailnet address (tailscale down) it listens on localhost only, so nodes cannot reach it. It refuses to start when the port is in use or a `--bind` is refused. To keep it running, a systemd user unit on the master, `~/.config/systemd/user/friday-dash.service`:

```
[Unit]
Description=friday dash
After=network-online.target tailscaled.service

[Service]
ExecStart=%h/friday/bin/friday dash
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
```

Adjust the path to the plugin folder (`plugin_dir`), then
`systemctl --user daemon-reload && systemctl --user enable --now friday-dash.service`.
`loginctl enable-linger $USER` keeps it running when you are logged out. Logs:
`journalctl --user -u friday-dash`.

## Running it in Docker

On the master, the dash can run as a Docker Compose service (`deploy/compose.yaml`, image built from
`deploy/Dockerfile`) instead of a foreground process or a systemd unit:

```
friday dash up      # docker compose -f <plugin>/deploy/compose.yaml up -d --build
friday dash down    # docker compose -f <plugin>/deploy/compose.yaml down
docker compose -f <plugin>/deploy/compose.yaml logs -f friday-dash   # logs
```

Both commands print the command they ran and fail with a clear message when `docker` is missing.
`up` passes `GH_TOKEN` from `gh auth token` through the environment (never on the command line or in
a file); when `gh` is signed out it is left unset with a note and the dash shows no PRs, so run
`gh auth login` and `friday dash up` again. The service is `restart: unless-stopped`, so it comes
back with the machine.

The container runs on the host network (so it binds the tailnet IP and sees real peer addresses),
mounts the registry file the CLI resolved (`$FRIDAY_NODES`, the plugin root `nodes.toml`, or `~/.config/friday/nodes.toml`) and `/var/run/tailscale/tailscaled.sock` read-only, and keeps
its state in the named volume `dash-state`. The security rules are unchanged: whois sender check,
bind only to `127.0.0.1` and the tailnet IP.

In the container the dash runs `friday dash --no-self`: it only receives reports and does not take
the master's own snapshot. The master therefore pushes its snapshot with its push timer like every
other node. Install the timer once on the master:

```
friday nodes --setup laptop     # use the master's registry name
```

A report from localhost is accepted as the master's. Until the timer is installed the master shows
as missing.

The foreground `friday dash` still works as described under "Starting it" and takes its own master
snapshot. Do not run it and the container at the same time: they use the same port.

## Setting up nodes

`friday nodes --setup <node>` sets the skip keys (see fleet.md) and, after the same y/N
confirmation, installs and enables `friday-push.timer` (30 s) in the node's
`~/.config/systemd/user/`, together with `friday-push.service`, which runs
`friday status --push`. The unit files come from `deploy/` in the plugin folder. A node without
python3 or systemd gets a message and no timer. The node must be in the registry, and the master
must have `role = "master"` there, because the push URL is built from it
(`http://<master tailnet or ssh host>:<[dash] port>`). Add `tailnet = "<device name>"` to a node
or the master when its tailnet name differs from the host in `ssh`.

`--setup` also writes `~/.config/friday/node.toml` on the node (`name`, `repos`, `dash` URL). A node
has no registry, so `friday status --push` takes its node name, repos and push URL from that file;
this is why the dash shows `alfred` and not the machine's hostname. See fleet.md.

## Stale and missing

- **ok**: the node reported within the last 90 s.
- **stale**: its last report is older than 90 s (the timer stopped, the node is off or offline).
  The last known state and its "last seen" time are still shown.
- **missing**: the node is in the registry but has never reported to this dash.

## Troubleshooting

- Push by hand on the node and read the answer: `friday status --push`
  (`--to http://<master>:8787` overrides the URL). 403 means the whois check failed: the device is
  not a registry node, or the node name differs from the device (set `tailnet`). 400 means a bad or
  oversize body.
- Connection refused or timeout: is `friday dash` running on the master
  (`curl http://127.0.0.1:8787/api/health` there), is the port the same in both registries, and is
  the node on the tailnet (`tailscale status`)?
- A node stays missing: check the timer, `systemctl --user list-timers friday-push.timer` and
  `journalctl --user -u friday-push` on the node.
- No PRs shown: `gh auth status` on the master.
- The dash refuses to start with `--bind 0.0.0.0`: by design.
