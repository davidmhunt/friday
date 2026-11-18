# gate-01: A directive with `Accept: user` waits for `friday accept` before its goal can land
Status: approved
Goal: v1-final
Node: any
Deliverable: code
Land: goal
Verify: uv run --with pytest pytest -q tests/test_accept_gate.py && uv run --with pytest pytest -q && claude plugin validate .
Hardware: none

## Goal
A directive may carry `Accept: user` (default `auto`). After Verify and the independent review
pass it becomes `Status: awaiting review`, the goal branch is pushed, and the run stops. Only
`friday accept <id>`, typed by the user, makes it `done`; `friday land --goal` refuses until
then. No agent can run `friday accept`. tests/test_accept_gate.py proves each of these.

## Steps
1. Format (lib/friday_core.py, `friday check`, `friday parse`): header `Accept: auto | user`
   (optional, default `auto`); directive status `awaiting review`; with `Accept: user` a
   `## Review` section is required with at least one `- ` bullet (what to open and what to look
   for). `external` directives must use `Accept: user` from now on (a warning, not an error, so
   old files still pass).
2. `friday finish <id>`: with `Accept: user` and no `--blocked`, write the record with
   `Status: awaiting review` and print the `## Review` bullets and the accept command.
   `friday accept <id> [--note TEXT]`: on the goal branch, only from `awaiting review`, append
   `Accepted by user: <date> <note>`, set `done`, one commit. `friday accept <id> --reject REASON`
   sets `blocked: <reason>` instead.
3. Ordering and landing: `friday start` treats an earlier `awaiting review` directive as
   finished for run order, so later directives continue; `friday land --goal` exits 7 and lists
   the directives still awaiting review.
4. Hook (hooks/friday_hook.py, PreToolUse Bash): deny any command that runs `friday accept`
   (also via `python3 .../bin/friday`, `uv run` and inside `ssh`), with the message that only the
   user accepts.
5. workflows/execute.js: after finish, if the directive is awaiting review, push the goal branch
   (`friday land <id>`), skip `land --goal`, and end with the review bullets and the two
   commands the user runs (`friday accept <id>`, `friday land --goal <g>`). The dispatched
   session prompt (lib/friday_fleet.py) reports the same to the planner session.
6. `friday status`, the status snapshot and the dash (dash/static/render.mjs) show
   `awaiting review` as its own state, counted on the Overview as needing the user.
7. tests/test_accept_gate.py and dash/static/render.test.mjs cases; skills/directive/SKILL.md and
   skills/plan/SKILL.md describe `Accept:` and `## Review`; CHANGELOG.

## Out of scope
- Accepting from the dashboard page.
- New deliverable types.

## Log
