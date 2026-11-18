# Dashboard (`friday dash`)

`friday dash` runs on the master and collects a status snapshot from every node in the registry
([fleet.md](fleet.md)). It is read-only: it serves state, it never acts on a repo or a node.

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
