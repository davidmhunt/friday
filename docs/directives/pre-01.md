# pre-01: A chained or multi-line command is pre-approved when every command in it is (fixes #17)
Status: approved
Goal: field-fixes
Node: any
Deliverable: code
Land: goal
Verify: uv run --with pytest pytest -q tests/test_preapproved.py && uv run --with pytest pytest -q && claude plugin validate .
Hardware: none

## Goal
Agents batch commands (several `ssh robot ...` lines, then a `grep`). Such a Bash call is allowed
without a prompt when every simple command in it, split by `fc.split_commands` on newlines,
`&&`, `||`, `;` and `|`, matches a pattern in the active directive's `## Allowed commands` (read
from `origin/<Base>` as today). It is never allowed when it contains command or process
substitution (`$(`, backticks, `<(`, `>(`) or a heredoc (`<<`), since those run text the check
does not see. There is no built-in list of "harmless" commands: helpers such as `grep *` are
pre-approved by listing them. Leases are taken for every hardware resource any part touches.
tests/test_preapproved.py proves it.

## Steps
1. hooks/friday_hook.py `check_preapproved`: replace the single-command requirement with: no
   substitution or heredoc anywhere; split into simple commands; each must match a pattern; any
   backgrounding `&` refuses. Reason text lists the patterns used.
2. Hardware: for a pre-approved batch, take the lease for each resource any part matches (in the
   order they appear); if another session holds one, deny as today naming it.
3. Guidance: skills/plan/SKILL.md says to list read-only helpers a directive's batches need
   (`grep *`, `cat runs/*`) under `## Allowed commands` and shows them in the approval summary;
   agents/implementer.md and agents/runner.md: hardware-touching commands one per line, no
   substitutions, so batches qualify. docs/spec.md updates the pre-approval rule.
4. tests/test_preapproved.py additions: a newline batch of three matching `ssh` lines and a
   matching `grep` is allowed; the same with one unmatched line asks as before; `$(...)`, a
   backtick, `<(` or `<<` in any line is not allowed; `&` backgrounding is not allowed; leases are
   taken for each resource; a lease held elsewhere denies. CHANGELOG (1.1.0 section) naming #17.

## Out of scope
- Classifying commands as harmless without the user listing them.

## Log
