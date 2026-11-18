# gate-03: Commands the user pre-approves in a directive run without a prompt during that directive
Status: approved
Goal: v1-final
Node: any
Deliverable: code
Land: goal
Verify: uv run --with pytest pytest -q tests/test_preapproved.py && uv run --with pytest pytest -q && claude plugin validate .
Hardware: none

## Goal
A directive may list `## Allowed commands`. While that directive is active in a worktree, the
PreToolUse hook allows a Bash command matching one of them, so a dispatched or overnight run that
needs `friday dispatch`, `friday nodes --clean`, `friday release` or a hardware command proceeds
without a prompt nobody is there to answer. The list is read from the directive as committed on
the goal's Base (the plan the user approved), so an agent editing the file on the goal branch
cannot widen it. Deny rules, `friday accept`, the commit guard and hardware leases still win.
tests/test_preapproved.py proves each of these.

## Steps
1. Format (lib/friday_core.py, `friday check`, `friday parse --json` as `allowed`): optional
   section `## Allowed commands`, bullets each holding one backticked command pattern where `*`
   matches any text. `friday check` errors on a pattern that is only `*`, contains `&&`, `;`, `|`
   or a backtick substitution, starts with `friday accept`, or matches the hook's deny list.
2. Hook (hooks/friday_hook.py pretool): with an active directive marker, read that directive from
   `git show <Base>:docs/directives/<id>.md`. If the command is one simple command (nothing
   chained) matching a pattern, emit `allow` with reason `pre-approved in <id> (on <Base>)`. Any
   deny from the deny list, run-only, commit guard or the `friday accept` rule beats it. A
   matching hardware command still takes the lease and is still denied while another session
   holds it, but is `allow` instead of `ask`. If Base has no copy or git fails, make no decision.
3. Skills: skills/plan/SKILL.md lists under `## Allowed commands` every prompted command a
   directive needs (dispatch, nodes --clean, release, hardware, ssh to a robot) and shows the
   section in the approval summary so the user approves it explicitly; skills/directive/SKILL.md
   documents the section and that it comes from Base; skills/hardware/SKILL.md says a
   pre-approved hardware command still takes the lease.
4. tests/test_preapproved.py: matching command allowed; a pattern only in the goal branch copy
   gives no decision; chained command not allowed; deny list beats a pattern; `friday accept`
   never allowed; no marker gives no decision; each `friday check` error; hardware pre-approved
   gives allow and takes the lease; lease held elsewhere gives deny.
5. CHANGELOG entry under Unreleased/Added.

## Out of scope
- Writing to `.claude/settings.json` or any standing allow rule (that stays the user's edit).
- Approvals that outlive the directive: once its marker is gone the list no longer applies.
- Adding the three prompted commands to the default allow rules (fix-02 keeps them prompted).

## Log
