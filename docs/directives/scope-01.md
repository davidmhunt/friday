# scope-01: Goals cover a whole capability, and related work extends the open goal instead of opening a new PR
Status: approved
Goal: field-fixes
Node: any
Deliverable: code
Land: goal
Verify: uv run --with pytest pytest -q tests/test_goal_scope.py && uv run --with pytest pytest -q && claude plugin validate .
Hardware: none

## Goal
A goal is one user-visible capability, typically 3 to 10 directives, and one PR; directives are
its reviewable units, landing as commits on the goal branch. Before planning, the plan skill
lists the repo's open goals (running, or done with an unmerged PR) and adds related work,
follow-ups, hardening and small fixes to one of them as a Base amendment; it proposes a new goal
only for unrelated work and states why. `friday status` and the dash show each goal's PR state,
so open goals are visible. Found from the PR history: about 18 PRs in two days, most
self-merged within minutes (approved by the user 2026-11-18). tests/test_goal_scope.py proves it.

## Steps
1. skills/plan/SKILL.md: replace "A goal is one planning run" and "Most goals are one to three
   directives" with the capability rule above; add a first step "find open goals" using
   `friday status --json` (goals not `done`, and `done` goals whose PR is open); the default for
   related work is adding directives to that goal (Base amendment, `friday check --goal`), and the
   approval summary says which goal is extended or why a new one is needed. A small fix with no
   open goal: offer to just do it (one-line fixes) or start a goal broad enough to take more.
2. Goal PR state: `friday status` (and `--json`) reports per goal `pr: none|open|merged` with the
   URL, via `gh pr list --head friday/<goal> --state all` (skipped quietly without `gh`); the dash
   shows it on the goal row. `friday land --goal` on a goal whose PR is already open pushes and
   says the PR was updated instead of opening another (verify current behaviour first; fix only
   if it opens a second PR or errors).
3. Docs: docs/spec.md (the model section: a goal is a capability, may span several planning runs,
   extended by Base amendments while its PR is open), docs/workflow.md and
   docs/getting-started.md say the same; skills/directive/SKILL.md one line.
4. tests/test_goal_scope.py: the plan skill no longer says "one to three" or "one planning run"
   and does name open goals and extension; `friday status --json` reports `pr` per goal from a
   fake `gh` (none, open, merged) and omits it quietly without `gh`; `land --goal` with an open PR
   does not open a second one. CHANGELOG in the 1.1.0 section.

## Out of scope
- Draft PRs, merging PRs automatically, or a standing maintenance goal.

## Log
