# review-03: Upstream commits merged in by `friday start` never count against a directive (fixes #21)
Status: approved
Goal: field-fixes
Node: any
Deliverable: code
Land: goal
Verify: uv run --with pytest pytest -q tests/test_directive_commits.py && uv run --with pytest pytest -q && claude plugin validate .
Hardware: none

## Goal
`friday commits <id>` (and so the review and `friday finish`) excludes every commit that reached
the goal branch through a Base merge: commits reachable from local `<Base>` or `origin/<Base>`,
and commits reachable only through the second parent of a merge made by `friday start` (or any
merge whose second parent is on Base). A teammate's upstream commits therefore never show as
`untracked`, while an untagged code commit made on the goal branch still does.
tests/test_directive_commits.py proves it.

## Steps
1. lib/friday_core.py `directive_commits`: list candidate commits with
   `git rev-list --no-merges HEAD --not <Base> origin/<Base>` (each ref only if it exists), and
   additionally drop commits reachable from the second parent of any merge in the range whose
   second parent is reachable from `origin/<Base>` or `<Base>` after a fetch. Keep the result's
   `base` field as the merge-base for display.
2. If a merge's second parent is not on Base (someone merged an unrelated branch), its commits
   stay candidates, so they still surface as `untracked`.
3. tests/test_directive_commits.py: origin/main gains a teammate commit after the plan commit;
   `friday start` merges it; `friday commits` lists no untracked line for it; an untagged code
   commit on the goal branch is still untracked; merging an unrelated branch still surfaces its
   commits. CHANGELOG in the 1.1.0 section (Fixed) naming #21.

## Out of scope
- Changing how `friday start` merges.

## Log
