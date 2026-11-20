# rel-03: Release 1.2.0
Status: approved
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
