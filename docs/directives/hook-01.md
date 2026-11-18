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

### 2026-11-18
Commits:
- b894714 hook-01: split_commands skips quoted heredoc bodies, scans substitutions in unquoted ones
- cebbe6f hook-01: friday init reports delete_branch_on_merge, status lists merged friday/* branches left on origin
- f641912 hook-01: tests for heredoc parsing and init/status branch reports; deny list skips quoted heredoc bodies; spec and CHANGELOG
- 626f74b hook-01: heredoc scan skips comments and arithmetic, reads partly quoted delimiters; tests
Verify: Verify passed: uv run --with pytest pytest -q tests/test_hook_parsing.py && uv run --with pytest pytest -q && claude plugin validate .
Independent review: not recorded
Blocked: review gaps remain: lib/friday_core.py:769 (_HEREDOC word class) and lib/friday_core.py:809-834 (_strip_heredocs); used by split_commands at :844 and by check_deny/check_accept in hooks/friday_hook.py: The fix in 626f74b handles the five reported inputs, but the underlying problem is still there. The scanner still starts heredocs bash never starts, and it still misreads delimiters bash does accept. The delimiter word only allows [A-Za-z0-9_.-], quoted parts and backslash escapes. Bash takes the whole shell word: '<<EOF+', '<<EOF@', '<<EOF:a', '<<EOF,' and '<<EOF'x' all end at the full word. The regex reads only 'EOF', so the body never closes and swallows every later line. On top of that, the arithmetic skip only covers '(('/''(('. In ''[1<<EOF]' and ''{x:-<<EOF}', bash starts no heredoc, but the scanner does. In both groups, real commands that bash runs are treated as heredoc body. The accept rule, deny list and commit/push guards then skip them. The new test (tests/test_hook_parsing.py:145-155) lists only the five earlier inputs, not the general class.

### 2026-11-18
Unblocked: was blocked: review gaps remain: lib/friday_core.py:769 (_HEREDOC word class) and lib/friday_core.py:809-834 (_strip_heredocs); used by split_commands at :844 and by check_deny/check_accept in hooks/friday_hook.py: The fix in 626f74b handles the five reported inputs, but the underlying problem is still there. The scanner still starts heredocs bash never starts, and it still misreads delimiters bash does accept. The delimiter word only allows [A-Za-z0-9_.-], quoted parts and backslash escapes. Bash takes the whole shell word: '<<EOF+', '<<EOF@', '<<EOF:a', '<<EOF,' and '<<EOF'x' all end at the full word. The regex reads only 'EOF', so the body never closes and swallows every later line. On top of that, the arithmetic skip only covers '(('/''(('. In ''[1<<EOF]' and ''{x:-<<EOF}', bash starts no heredoc, but the scanner does. In both groups, real commands that bash runs are treated as heredoc body. The accept rule, deny list and commit/push guards then skip them. The new test (tests/test_hook_parsing.py:145-155) lists only the five earlier inputs, not the general class.

### 2026-11-18
Commits:
- b894714 hook-01: split_commands skips quoted heredoc bodies, scans substitutions in unquoted ones
- cebbe6f hook-01: friday init reports delete_branch_on_merge, status lists merged friday/* branches left on origin
- f641912 hook-01: tests for heredoc parsing and init/status branch reports; deny list skips quoted heredoc bodies; spec and CHANGELOG
- 626f74b hook-01: heredoc scan skips comments and arithmetic, reads partly quoted delimiters; tests
- 9e4dcbe hook-01: split_commands skips only quoted plain-word heredoc bodies, fails closed on everything else
- f063703 hook-01: tests for the fail-closed heredoc cases; spec and CHANGELOG describe the narrowed rule
- 9a5e881 hook-01: heredoc skip fails closed after an earlier opener on the line and after ) comments
Verify: Verify passed: uv run --with pytest pytest -q tests/test_hook_parsing.py && uv run --with pytest pytest -q && claude plugin validate .
Independent review: not recorded
Blocked: review gaps remain: /home/david/Documents/claude_temp/friday/lib/friday_core.py:805-806 (_heredoc_at earlier-opener guard), used by _strip_heredocs and so by split_commands, check_accept and check_deny: Step 1 requires every unquoted heredoc to be scanned in full. The new guard only looks for an earlier '<<' on the same physical line as the quoted opener. The scanner never tracks where an unquoted heredoc's body ends, so a quoted opener on a line inside an unquoted heredoc's body is still taken as a real heredoc. The scanner then skips from that line down to the quoted delimiter, and that span includes the rest of the unquoted body. bash expands ''(...)' and backticks there, so they run without being judged. Fixing commit 9a5e881 patched the same-line and ';' forms that were reported, but the same fail-open class stays open one line later.

### 2026-11-18
Unblocked: was blocked: review gaps remain: /home/david/Documents/claude_temp/friday/lib/friday_core.py:805-806 (_heredoc_at earlier-opener guard), used by _strip_heredocs and so by split_commands, check_accept and check_deny: Step 1 requires every unquoted heredoc to be scanned in full. The new guard only looks for an earlier '<<' on the same physical line as the quoted opener. The scanner never tracks where an unquoted heredoc's body ends, so a quoted opener on a line inside an unquoted heredoc's body is still taken as a real heredoc. The scanner then skips from that line down to the quoted delimiter, and that span includes the rest of the unquoted body. bash expands ''(...)' and backticks there, so they run without being judged. Fixing commit 9a5e881 patched the same-line and ';' forms that were reported, but the same fail-open class stays open one line later.
