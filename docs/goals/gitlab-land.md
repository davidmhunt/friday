# gitlab-land: Goals land on GitLab as merge requests, and on any other remote as a pushed branch
Status: approved
Base: main
Land: pr

## Goal
Issue #20. Landing, merged checks and the dash's PR list use `gh`, so a repo whose origin is a
self-hosted GitLab cannot use `Land: pr` (the workaround is `Land: none` and a hand-made MR).
The user chose on 2026-11-20: detect the forge from origin with a `forge` override in
.claude/friday.json (`github | gitlab | none`); on GitLab use `glab` for the merge request and for
status, dash and merged-branch checks; any other remote gets `Land: push` (reverify, push the
branch, print the compare/MR URL); `friday check` warns when `Land: pr` cannot work. GitHub
behaviour is unchanged. Tested with fake `glab`; a live run against the user's GitLab project is a
later step the user will arrange ("we can get there when we get there").

The user approved the goal and its directives on 2026-11-20.

## Directives
1. fg-01: friday knows each repo's forge (github, gitlab or none) and `friday check` warns when `Land: pr` cannot work
2. fg-02: `Land: push` reverifies, pushes the goal branch and prints the compare URL, opening nothing
3. fg-03: On GitLab, `friday land` opens or finds a merge request with glab
4. fg-04: On GitLab, merged-goal detection, `friday status` and the dash's open-PR list use glab

## Log
