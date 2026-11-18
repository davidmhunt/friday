# attention: Nothing a run needs from the user goes unnoticed or uncommitted
Status: approved
Base: v1
Land: pr

## Goal
Three follow-ups found while landing 1.0. `friday accept` refuses while the user's review work
(a routed board, an edited figure) is uncommitted, so it cannot be left out of the goal. A
dispatched session stuck on any prompt shows on the dashboard as needing the user, and the
planner session's check can read it. Heredoc text stays fully scanned (documented workaround: a body
file), and friday reports merged goal branches left on GitHub. All three approved by the user on
2026-11-18; rel-02 (release as 1.1.0) added with the user's approval the same day.

## Directives
1. accept-01: `friday accept` refuses while tracked files are uncommitted, and says how to commit them
2. attn-01: A session waiting on a prompt shows as needing the user on the dash and to the planner
3. hook-01: Heredoc text stays fully scanned (documented), and friday reports merged branches left on origin
4. rel-02: Release 1.1.0, installed from main

## Log
