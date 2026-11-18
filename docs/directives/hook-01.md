# hook-01: Heredoc text stays fully scanned (documented), and friday reports merged branches left on origin
Status: approved
Goal: attention
Node: any
Deliverable: code
Land: goal
Verify: uv run --with pytest pytest -q tests/test_hook_parsing.py && uv run --with pytest pytest -q && claude plugin validate .
Hardware: none

## Goal
The PreToolUse checks keep scanning every heredoc body in full. Two review rounds showed that
exempting quoted heredocs can hide real commands in unusual inputs, so the user chose fail-safe
false positives over a parser making security decisions (amended 2026-11-18). Long text that
names a guarded command goes in a file passed with `--body-file`/`-F`, and the docs say so. And
GitHub stays tidy: friday reports merged goal branches left on origin.

## Steps
1. lib/friday_core.py `split_commands`: remove the heredoc exemption added on this goal branch
   (`_strip_heredocs`, `_heredoc_at` and their callers), so every heredoc body is scanned as
   before hook-01. docs/spec.md known limits, skills/directive/SKILL.md and the PR/commit advice in
   workflows/execute.js (if any) say: text naming a guarded command goes in a file passed with
   `--body-file`/`-F`, not a heredoc.
2. Branch hygiene: `friday init` reports whether the GitHub repo deletes head branches on merge
   (`gh api repos/<owner>/<repo> --jq .delete_branch_on_merge`) and prints the command to turn it
   on; it changes nothing. `friday status` lists `origin/friday/*` branches whose PR is merged,
   with `git push origin --delete <branch>` for each; it deletes nothing. Both skip quietly when
   `gh` is unavailable or signed out.
3. tests/test_hook_parsing.py: a quoted heredoc whose text names the accept command is still
   refused (the documented limit); the same text in a file passed with `--body-file` passes;
   the reviewer's earlier fail-open inputs are refused; init and status report from a fake `gh`.
   Spec and CHANGELOG.

## Out of scope
- Deleting branches or changing repository settings.
- Any heredoc exemption.

## Log
