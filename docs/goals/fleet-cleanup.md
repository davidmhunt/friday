# fleet-cleanup: Dispatched work cleans up after itself on the node
Status: approved
Base: v1
Land: pr

## Goal
Nodes stop accumulating idle sessions, worktrees and branches: a dispatched session that
finishes its goal exits and its tmux session closes (a blocked one stays open to be unblocked),
and worktrees, local goal branches and trust entries of goals whose PR is merged are removed,
automatically before each dispatch to a node and on demand with `friday nodes --clean <node>`.
Unmerged or dirty worktrees are never removed. Asked for by the user after the fleet and
fleet-hardening runs left two idle sessions, two worktrees and a stray clone on Alfred.

## Directives
1. fleet-06: A dispatched session that lands its goal ends its own tmux session
2. fleet-07: `friday nodes --clean <node>` removes merged goals' worktrees; dispatch runs it first
3. fleet-08: `friday dispatch --goal <g> --resume` restarts a stopped goal in its existing worktree

## Log
