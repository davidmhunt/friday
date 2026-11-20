# push-container: A node can push its status from a container instead of a host systemd timer
Status: done
Base: main
Land: pr

## Goal
Issue #13. `friday nodes --setup <node>` installs `friday-push.timer`, a systemd user unit that runs
`friday status --push` every 30 s. Owners who keep development tooling off the host want a
container instead. After this goal a node in nodes.toml can set `push = "container"` (default
`"timer"`, today's behaviour): setup then runs a long-lived push container from the same
`friday-dash:local` image the dash uses (one image per machine, no second image), with
`restart: unless-stopped` in place of the timer, and the snapshot it pushes is the same as the
timer's: friday-* tmux sessions, repos, leases, health, GPUs where the NVIDIA runtime exists.
It must work on x86_64 workers (Alfred) and arm64 Jetson robots. The user chose this design on
2026-11-20 (opt-in per node, reuse the dash image, mounts for repos/node.toml/leases/tmux socket,
your uid, GPUs when available).

The user approved the goal and its directives on 2026-11-20.

## Directives
1. pc-01: `friday status --push --every N` loops, and the snapshot can read the host through mounted paths
2. pc-02: `push = "container"` nodes get a push container from the dash image instead of the systemd timer

## Log
- 2026-11-20: Landed: 2 directive(s) reverified on friday/push-container; PR into main.
