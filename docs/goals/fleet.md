# fleet: Run directives on other machines
Status: running
Base: v1
Land: pr

## Goal
friday routes a goal to one node that satisfies its directives' `Node:` lines, runs it there on
`friday/<goal>`, and documents the fleet setup.

## Directives
1. fleet-01: Node registry and routing (`friday nodes`)
2. fleet-02: `friday dispatch --goal <g>` runs a goal on another node and reports back
3. fleet-03: Fleet docs and planning hand-off

## Log
