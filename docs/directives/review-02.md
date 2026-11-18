# review-02: The plan changes only on Base, `friday start` merges Base in, and git refuses stray commits during a directive
Status: approved
Goal: review-range
Node: any
Deliverable: code
Land: goal
Verify: uv run --with pytest pytest -q tests/test_plan_on_base.py && uv run --with pytest pytest -q && claude plugin validate .
Hardware: none

## Goal
An approved plan lives on the goal's Base; amendments are commits there. Before each directive,
`friday start` merges Base into the goal branch, so plan amendments and harness fixes reach a
running goal only between directives. While a directive is active in a worktree, a `commit-msg`
git hook installed by friday refuses any commit without `Directive: <active id>`, whoever makes
it (agent, ssh, terminal). Approved by the user after v1-final's fix-02 blocked on a plan commit
made on its goal branch mid-run. tests/test_plan_on_base.py proves each of these.

## Steps
1. `friday start <id>`: after switching to the goal branch and before writing the marker, if the
   Base (`origin/<Base>` after a fetch, else local; a failed or timed-out fetch warns and uses the
   local branch) is not an ancestor of HEAD, run
   `git merge --no-edit <Base>` with the message `Merge <Base> into friday/<goal> before <id>`
   and the trailer `Directive: <id>`. On conflict run `git merge --abort`, exit non-zero with the
   conflicting paths, and change nothing else. Print `merged <Base> <sha>` when it merged.
   `Land: pr` directives do the same on `friday/<id>`. A dirty tree still refuses as today.
2. Git guard: `friday init` and `friday start` install `commit-msg` into the repo's hooks
   directory (`git rev-parse --git-common-dir`/hooks, or `core.hooksPath` when set). The hook
   reads the worktree's marker (`$(git rev-parse --git-dir)/friday-active`); with no marker it
   exits 0; with one it refuses a message without the line `Directive: <id>`, unless every staged file
   is under `docs/goals/` or `docs/directives/` and the message names a directive of the same
   goal (friday's record commits, `friday accept` of an earlier directive); it says how to
   commit (`git commit --no-verify` to override deliberately). An existing `commit-msg` that is
   not friday's is moved to `commit-msg.local` and called first, its exit code respected.
   Re-installing is idempotent. `friday uninstall` removes friday's hook and restores the local one.
3. PreToolUse commit guard (hooks/friday_hook.py): evaluate the repository the command commits
   in (`cd DIR && git commit`, `git -C DIR commit`), not the session's cwd, so a commit in another
   worktree is judged by that worktree's marker and branch. Drop its trailer check, which the
   git hook now enforces for every committer; keep the main/master/Base protection.
4. Docs and skills: skills/plan/SKILL.md and skills/directive/SKILL.md say amendments to an
   approved goal are commits on Base checked with `friday check`, picked up at the next
   `friday start`, and that an amendment to the running directive takes effect when it restarts.
   docs/workflow.md and docs/fleet.md say the same; CHANGELOG entries under Unreleased.
5. tests/test_plan_on_base.py on a temp repo with a goal branch: a commit on Base appears on the
   goal branch after the next start (merge commit carries the trailer and `friday commits`, if
   present, lists no untracked line for it); a conflicting Base change makes start exit non-zero
   with the path and leaves HEAD and the tree unchanged; with a marker the hook refuses a commit
   without the trailer and allows one with it; with no marker it allows any commit; an existing
   commit-msg hook is preserved and still runs; install twice leaves one hook; uninstall restores;
   a record-only commit naming another directive of the goal passes the hook; a failed fetch
   falls back to the local Base; the PreToolUse guard judges `git -C <other worktree> commit` by
   that worktree.

## Out of scope
- Rewriting history on any branch.
- Hooks other than `commit-msg`; server-side enforcement.
- Changing v1-final's directives; v1-final picks this up through step 1 at its next start.

## Log
