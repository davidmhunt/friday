# fleet: Run directives on other machines
Status: approved
Base: v1
Land: pr

## Goal
friday routes a directive to the node that satisfies its `Node:` line, dispatches it there, and
documents the fleet setup.

## Directives
1. fleet-01: Node registry and routing (`friday nodes`)
2. fleet-02: `friday dispatch <id>` starts a directive on another node and reports back
3. fleet-03: Fleet docs and planning hand-off

## Log
