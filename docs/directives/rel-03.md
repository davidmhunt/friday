# rel-03: Release 1.2.0
Status: blocked: Do you approve the Verify change in commit 2773f6f? It went from 'uv run --with pytest pytest -q ...' to 'uv run --with pytest --with pyyaml pytest -q ...'. I recommend approving it as is. The edit only adds '--with pyyaml', which the suite imports (the block reason was 'ModuleNotFoundError: No module named 'yaml''), and it matches the repo's default Verify in CLAUDE.md. It doesn't weaken the check. The gap is real. The plan edit was made during execution by an agent, and nothing records your approval. I can't supply that approval myself, and a new commit can't remove the edit from history. Reverting would only bring back a Verify that can't pass. Once you approve, record it in the review, or tell me to add a note or take another route.
Goal: release-1-2
Node: any
Deliverable: code
Land: goal
Verify: uv run --with pytest --with pyyaml pytest -q tests/test_release.py && uv run --with pytest --with pyyaml pytest -q && claude plugin validate .
Hardware: none

## Goal
Everything on main since 1.1.0 (goal thin-targets, PR #26, cm-01 and py-01) ships as friday 1.2.0: the
version in .claude-plugin/plugin.json and .claude-plugin/marketplace.json is `1.2.0`, and
CHANGELOG.md has a `1.2.0 - 2026-11-19` section. The version change is what lets `/plugin update`
refresh installed copies (it skips a cache already at 1.1.0). Requested by the user on 2026-11-19.

## Steps
1. .claude-plugin/plugin.json and .claude-plugin/marketplace.json: version `1.2.0`. CHANGELOG.md:
   turn `Unreleased` into `1.2.0 - 2026-11-19` with a one-line summary on top (a uv-managed Python private to friday,
   rules, thin targets, plan on the goal branch, #30), add an empty `Unreleased`. The summary names
   the steps a user must take on upgrade (uv is required; run `friday install` again on each
   machine; goals with Allowed commands need the user's one-time plan publish).
2. tests/test_release.py still passes (marketplace version equals plugin.json's); no other change
   needed unless it checks the changelog heading.

## Out of scope
- Merging the PR, tagging `v1.2.0`, updating installed copies: done after the user merges.

## Log

### 2026-11-20
Commits:
- 7a411fd rel-03: version 1.2.0 and changelog section
Verify: not run
Independent review: not recorded
Blocked: Verify still fails after 2 round(s): E ModuleNotFoundError: No module named 'yaml'

### 2026-11-20
Unblocked: was blocked: Verify still fails after 2 round(s): E ModuleNotFoundError: No module named 'yaml'

### 2026-11-20
Commits:
- 7a411fd rel-03: version 1.2.0 and changelog section
Verify: Verify passed: uv run --with pytest --with pyyaml pytest -q tests/test_release.py && uv run --with pytest --with pyyaml pytest -q && claude plugin validate .
Independent review: not recorded
Blocked: Do you approve the Verify change in commit 2773f6f? It went from 'uv run --with pytest pytest -q ...' to 'uv run --with pytest --with pyyaml pytest -q ...'. I recommend approving it as is. The edit only adds '--with pyyaml', which the suite imports (the block reason was 'ModuleNotFoundError: No module named 'yaml''), and it matches the repo's default Verify in CLAUDE.md. It doesn't weaken the check. The gap is real. The plan edit was made during execution by an agent, and nothing records your approval. I can't supply that approval myself, and a new commit can't remove the edit from history. Reverting would only bring back a Verify that can't pass. Once you approve, record it in the review, or tell me to add a note or take another route.
