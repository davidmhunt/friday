# release-1-2: Earlier directives' merges stop blocking later reviews, and friday ships as 1.2.0
Status: approved
Base: main
Land: pr

## Goal
Fix issue #30 (`friday commits` lists commits an earlier directive merged in as `untracked` for every
later directive in the goal, so each later review blocks), then release everything on main since
1.1.0 (the thin-targets goal and this fix) as friday 1.2.0. Requested by the user on 2026-11-19.

## Directives
1. cm-01: A commit already on the goal branch when a directive starts is not reported as its untracked work (fixes #30)
2. rel-03: Release 1.2.0

## Log
