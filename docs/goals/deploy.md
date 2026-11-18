# deploy: Every machine reports to a dash that runs in Docker, with no hand setup
Status: done
Base: v1
Land: pr

## Goal
The last step before v1 ships (the user's final-design run, 2026-11-17). After
`friday nodes --setup <node>`, each node knows who it is, which repos it holds and where the dash
is, without its own copy of the registry, so its pushes are accepted. The dash runs as a
Docker Compose service on the master (`friday dash up` / `friday dash down`), chosen by the user
because it is consistent across machines and easy to bring up and down. `friday nodes --check`
shows whether each node is reporting, and docs/dashboard.md explains how machines and projects get
onto the page. A reader can tell it holds when, after `friday dash up` and `--setup` on the laptop
and Alfred, both machines show `ok` on the page with their repos.

Decided, not built here: acting on goals from the page is a later goal; `v1` merges into `main`
as the v1 release after this goal lands and the live check passes.

## Directives
1. node-01: `--setup` writes the node's identity file; `friday status --push` uses it with no registry
2. dash-01: `friday dash` runs as a Docker Compose service on the master
3. dash-02: `friday nodes --check` shows each node's dash status; the docs explain registration

## Log
- 2026-11-17: Landed: 3 directive(s) reverified on friday/deploy; PR into v1.
