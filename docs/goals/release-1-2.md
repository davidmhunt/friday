# release-1-2: Earlier directives' merges stop blocking later reviews, and friday ships as 1.2.0
Status: blocked: cm-01
Base: main
Land: pr

## Goal
Fix issue #30 (`friday commits` lists commits an earlier directive merged in as `untracked` for every
later directive in the goal, so each later review blocks), then release everything on main since
1.1.0 (the thin-targets goal and this fix) as friday 1.2.0. Requested by the user on 2026-11-19.
py-01 added on 2026-11-19 at the user's request after cm-01's Verify showed that `friday install`
had made uv's managed 3.12 the default for every `uv run` on the machine. cm-01's Verify now declares
pyyaml (commit fe3e96e, from the fix round): the suite imports it, so it is a real test dependency.

## Directives
1. cm-01: A commit already on the goal branch when a directive starts is not reported as its untracked work (fixes #30)
2. py-01: friday's uv-managed Python is private to friday: it is not on PATH and other projects' `uv run` never picks it
3. rel-03: Release 1.2.0

## Log
