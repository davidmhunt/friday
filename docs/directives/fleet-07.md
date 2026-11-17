# fleet-07: `friday nodes --clean <node>` removes merged goals' worktrees; dispatch runs it first
Status: approved
Goal: fleet-cleanup
Node: any
Deliverable: code
Land: goal
Verify: uv run --with pytest pytest -q tests/test_node_clean.py tests/test_dispatch.py && uv run --with pytest pytest -q && claude plugin validate .
Hardware: none

## Goal
`friday nodes --clean <node> [--dry-run]` finds goal worktrees under the node's `repos`
(`<repos>/<repo>.friday/<goal>`), decides on the master which goals are finished (their
`friday/<goal>` PR is merged, or the branch is gone from origin), and on the node removes each
finished goal's worktree, local branch, the trust entry fleet-04 added and a leftover
`friday-<goal>` tmux session. It keeps anything unmerged, dirty or still running and lists why.
`friday dispatch` runs the same clean (no prompt) for the target node before preparing. Clones
whose folder name doesn't match their origin repo are reported, never deleted.
tests/test_node_clean.py proves every keep and remove case against a fake `ssh` and `gh`.

## Steps
1. Inventory script (via `friday_fleet.ssh_cmd`): for each `<repos>/*.friday/*` worktree print repo,
   goal, branch, HEAD, whether tracked or untracked files are dirty (ignoring `runs/`), whether a
   `friday-<goal>` tmux session exists and whether its pane is at an idle prompt; also list git
   clones under `<repos>` whose folder name differs from their origin repo name.
2. Decide on the master: a goal is finished when `gh pr list --state merged --head friday/<goal>`
   finds a PR (squash merges break ancestry, so do not use `git branch --merged`), or when
   `friday/<goal>` no longer exists on origin and the goal file in the worktree says `done`. Keep
   when unfinished, dirty, or its session is not idle; each kept item gets a one-line reason.
   Without gh, fall back to the branch-gone rule only and say so.
3. Clean script: for finished goals, `tmux kill-session -t =friday-<goal>` (only if idle),
   `git worktree remove` (never `--force`), `git branch -D friday/<goal>` in the clone,
   `git worktree prune`, and remove `projects[<worktree path>]` from `~/.claude.json` (temp file +
   rename, other keys kept). `--dry-run` prints the plan and changes nothing.
4. `friday dispatch` runs the clean for the target node before the prepare script, printing what
   it removed; a clean failure is reported but does not block the dispatch.
5. Add `tests/test_node_clean.py`: merged PR removes worktree, branch, trust entry and idle
   session; unmerged, dirty and busy-session goals are kept with reasons; branch-gone fallback
   without gh; a squash-merged branch is detected via gh; stray clone reported, not deleted;
   `--dry-run` changes nothing; dispatch calls clean first and proceeds when clean fails.
6. docs/fleet.md: the clean rules, `--clean`, and that stray clones must be removed by hand.
   CHANGELOG entry.

## Out of scope
- Deleting remote branches (enable GitHub's "delete branch on merge" instead).
- Deleting clones, stray or not; cleaning the master's own checkout.
- Sessions ending themselves (fleet-06).

## Log
