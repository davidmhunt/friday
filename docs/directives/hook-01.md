# hook-01: The hook ignores quoted heredoc text, and friday reports merged branches left on origin
Status: approved
Goal: attention
Node: any
Deliverable: code
Land: goal
Verify: uv run --with pytest pytest -q tests/test_hook_parsing.py && uv run --with pytest pytest -q && claude plugin validate .
Hardware: none

## Goal
The PreToolUse checks (deny list, the accept rule, commit and push guards) judge what a command
runs, not text it passes as data: the body of a quoted heredoc (`<<'EOF'`, `<<"EOF"`, `<<\EOF`) is
not scanned, while an unquoted heredoc's `$(...)` and backticks still are, because the shell runs
them. Found when a `gh pr create --body-file - <<'EOF'` whose PR text named the accept command
was refused. And GitHub stays tidy: friday reports merged goal branches left on origin.

## Steps
1. lib/friday_core.py `split_commands`: recognise heredocs; drop the body of a quoted heredoc
   from command and substitution scanning; keep scanning substitutions in an unquoted one.
2. Branch hygiene: `friday init` reports whether the GitHub repo deletes head branches on merge
   (`gh api repos/<owner>/<repo> --jq .delete_branch_on_merge`) and prints the command to turn it
   on; it changes nothing. `friday status` lists `origin/friday/*` branches whose PR is merged,
   with `git push origin --delete <branch>` for each; it deletes nothing. Both skip quietly when
   `gh` is unavailable or signed out.
3. tests/test_hook_parsing.py: quoted heredoc text naming the accept command, `sudo` and
   backticks passes; the same in an unquoted heredoc's substitution is still refused; a real
   accept command after the heredoc is still refused; init and status report from a fake `gh`.
   Spec and CHANGELOG.

## Out of scope
- Deleting branches or changing repository settings.

## Log
