# fleet-hardening: Dispatch with no first-run prompts on the node
Status: approved
Base: v1
Land: pr

## Goal
A goal dispatched to a node set up per docs/fleet.md runs with no manual step on the node, even
the first time: dispatch trusts the new worktree itself, names it after the repo's origin, and
`friday nodes --check` reports every node-side prompt that would block a dispatched session, with
`friday nodes --setup <node>` to clear them. Found in the first live dispatch (fleet, PR #3),
which stopped at the folder trust and workflow approval prompts on Alfred.

## Directives
1. fleet-04: Dispatch trusts the new worktree and names it from origin
2. fleet-05: `friday nodes --check` reports blocking prompts; `friday nodes --setup <node>`

## Log
