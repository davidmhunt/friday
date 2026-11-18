# hook-01: The hook ignores quoted heredoc text, and friday reports merged branches left on origin
Status: blocked: review gaps remain: lib/friday_core.py:769 (_HEREDOC word class) and lib/friday_core.py:809-834 (_strip_heredocs); used by split_commands at :844 and by check_deny/check_accept in hooks/friday_hook.py: The fix in 626f74b handles the five reported inputs, but the underlying problem is still there. The scanner still starts heredocs bash never starts, and it still misreads delimiters bash does accept. The delimiter word only allows [A-Za-z0-9_.-], quoted parts and backslash escapes. Bash takes the whole shell word: '<<EOF+', '<<EOF@', '<<EOF:a', '<<EOF,' and '<<EOF'x' all end at the full word. The regex reads only 'EOF', so the body never closes and swallows every later line. On top of that, the arithmetic skip only covers '(('/''(('. In ''[1<<EOF]' and ''{x:-<<EOF}', bash starts no heredoc, but the scanner does. In both groups, real commands that bash runs are treated as heredoc body. The accept rule, deny list and commit/push guards then skip them. The new test (tests/test_hook_parsing.py:145-155) lists only the five earlier inputs, not the general class.
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

### 2026-11-18
Commits:
- b894714 hook-01: split_commands skips quoted heredoc bodies, scans substitutions in unquoted ones
- cebbe6f hook-01: friday init reports delete_branch_on_merge, status lists merged friday/* branches left on origin
- f641912 hook-01: tests for heredoc parsing and init/status branch reports; deny list skips quoted heredoc bodies; spec and CHANGELOG
- 626f74b hook-01: heredoc scan skips comments and arithmetic, reads partly quoted delimiters; tests
Verify: Verify passed: uv run --with pytest pytest -q tests/test_hook_parsing.py && uv run --with pytest pytest -q && claude plugin validate .
Independent review: not recorded
Blocked: review gaps remain: lib/friday_core.py:769 (_HEREDOC word class) and lib/friday_core.py:809-834 (_strip_heredocs); used by split_commands at :844 and by check_deny/check_accept in hooks/friday_hook.py: The fix in 626f74b handles the five reported inputs, but the underlying problem is still there. The scanner still starts heredocs bash never starts, and it still misreads delimiters bash does accept. The delimiter word only allows [A-Za-z0-9_.-], quoted parts and backslash escapes. Bash takes the whole shell word: '<<EOF+', '<<EOF@', '<<EOF:a', '<<EOF,' and '<<EOF'x' all end at the full word. The regex reads only 'EOF', so the body never closes and swallows every later line. On top of that, the arithmetic skip only covers '(('/''(('. In ''[1<<EOF]' and ''{x:-<<EOF}', bash starts no heredoc, but the scanner does. In both groups, real commands that bash runs are treated as heredoc body. The accept rule, deny list and commit/push guards then skip them. The new test (tests/test_hook_parsing.py:145-155) lists only the five earlier inputs, not the general class.
