# status-page: A tailnet dashboard of machines, projects and running sessions
Status: approved
Base: v1
Land: pr

## Goal
Phase 4 (HANDOFF section 6), reshaped with the user: every node reports a snapshot of itself
(`friday status --json`: health, GPU, friday work, running sessions with what they are doing),
pushes it to `friday dash` on the master over the tailnet, and the master serves a read-only
dashboard modelled on Jarvis OS (`../jarvis/jarvis_os`): an Overview (needs-you strip, machine
cards, project cards) with Machines, Projects and Sessions tabs. A reader can tell it holds by
opening the page on the phone and seeing each machine's summary, each project's goals and
directive statuses, and which session runs which directive where. Acting on goals from the page
is a later goal; this one never writes to a repo or a node.

## Directives
1. status-01: `friday status --json` reports one node's health, GPU, friday work and sessions
2. status-02: `friday dash` collects node reports pushed over the tailnet, read-only API
3. status-03: Dashboard UI modelled on Jarvis OS: Overview, Machines, Projects, Sessions

## Log
- 2026-11-17: reshaped with the user before approval: a per-machine summary, a Jarvis-inspired
  dashboard instead of one static page, node push over the tailnet instead of SSH pull, pane
  snippets for running sessions; acting on goals deferred.
