# rel-01: Release 1.0.0
Status: approved
Goal: v1-final
Node: any
Deliverable: code
Land: goal
Verify: uv run --with pytest pytest -q tests/test_release.py && uv run --with pytest pytest -q && claude plugin validate .
Hardware: none

## Goal
The plugin says 1.0.0 everywhere and can be installed from a marketplace entry: version,
changelog, licence and install instructions agree, proved by tests/test_release.py.

## Steps
1. .claude-plugin/plugin.json: version `1.0.0`. CHANGELOG.md: turn `Unreleased` into
   `1.0.0 - <date>` with a short summary on top, add an empty `Unreleased`, remove the lines about
   the `VERSION` file.
2. Add `LICENSE` (MIT, the user as holder) and `.claude-plugin/marketplace.json` listing this
   plugin, so `/plugin marketplace add` works on a clone.
3. README.md: drop "alpha"; install section uses the marketplace; Status says 1.0 and links the
   spec, tutorial and changelog.
4. tests/test_release.py: plugin.json version equals the top released CHANGELOG heading;
   marketplace.json parses and names the plugin; LICENSE exists; README has no "alpha".

## Out of scope
- Tagging, merging v1 into main, and changing the GitHub default branch: the user does these after merging the goal PR.

## Log
