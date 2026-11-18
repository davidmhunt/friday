# gate-01: A directive with `Accept: user` waits for `friday accept` before its goal can land
Status: done
Goal: v1-final
Node: any
Deliverable: code
Land: goal
Verify: uv run --with pytest pytest -q tests/test_accept_gate.py && uv run --with pytest pytest -q && claude plugin validate .
Hardware: none

## Goal
A directive may carry `Accept: user` (default `auto`). After Verify and the independent review
pass it becomes `Status: awaiting review` and the goal branch is pushed; the run moves on to
the next directive, and the goal lands only after the user accepts. Only
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
   commands the user runs (`friday accept <id>`, `friday land --goal <g>`), then continue with the
   next directive. When the last directive ends and some are awaiting review, the dispatched
   session (lib/friday_fleet.py) reports once to the planner session:
   `review <goal> <ids> PR-pending` (alongside the existing `done` and `blocked` messages) and
   stays open.
6. `friday status`, the status snapshot and the dash (dash/static/render.mjs) show
   `awaiting review` as its own state, counted on the Overview as needing the user.
7. tests/test_accept_gate.py and dash/static/render.test.mjs cases, including `friday accept`
   of an earlier directive while a later one is active in the same worktree (its record commit
   must pass the commit guard and the commit-msg hook); `friday accept` joins the user-only list
   in tests/test_cli_surface.py; skills/directive/SKILL.md and
   skills/plan/SKILL.md describe `Accept:` and `## Review`; CHANGELOG.

## Out of scope
- Accepting from the dashboard page.
- New deliverable types.

## Log

### 2026-11-18
Commits:
- a761a9a gate-01 step 1: Accept: auto|user header, awaiting review status, ## Review section; external without Accept: user warns
- c428b2e gate-01 step 2: friday finish writes awaiting review for Accept: user; friday accept [--note|--reject]
- fc1bcd9 gate-01 step 2: document friday accept in the README
- e7b98b1 gate-01 step 3: friday start treats awaiting review as finished for order; land --goal exit 7 names awaiting-review directives
- 97a9d2d gate-01 step 4: hook denies friday accept (direct, python3, uv run, ssh, bash -c)
- 6f39531 gate-01 step 5: execute.js pushes and skips land --goal when awaiting review; fleet session reports review <goal> <ids> PR-pending
- 76d76e1 gate-01 step 6: awaiting review is its own state in friday status, the snapshot and the dash, counted as needing the user
- 44e9b1c gate-01 step 7: accept is on the user-only list in the surface test; directive and plan skills describe Accept and Review; CHANGELOG
- 8a138e0 gate-01: execute.js reports awaiting review with bullets and friday accept for Land none and Land pr too
Notes:
2026-11-18: Dispatched from thinkpadP15v3 to cpsl-homebase
Verify: Verify passed: uv run --with pytest pytest -q tests/test_accept_gate.py && uv run --with pytest pytest -q && claude plugin validate .
Independent review: gaps fixed in second review: 1. /home/david/Documents/claude_temp/friday.friday/v1-final/workflows/execute.js:273 (and :278): The awaiting-review branch (line 287) is only reached for Land goal. A directive with 'Land: none' returns at line 273, and one with 'Land: pr' returns at 278-281. Both use 'head' = ''{id} done: ...', so the workflow reports the directive as done and never shows the '## Review' bullets or the 'friday accept <id>' command. 'Deliverable: external' must have 'Land: none', and this directive says external directives must use 'Accept: user'. So the main use case for the gate ends with a final message saying it is done, while the file says 'awaiting review' and the goal cannot land. Step 5 says that after finish, an awaiting-review directive ends with the review bullets and the commands the user runs. No test covers Land none or Land pr with Accept: user: test_awaiting_review_branch_skips_land_goal only checks the source text after 'runLand(landCmd'. (evidence: execute.js:272 'const head = ''{id} done: ...''; :273 'if (landMode === 'none') return ''{head} Land none: committed only, nothing pushed.''; :287 'if (d.accept === 'user') {' comes after both early returns. lib/friday_core.py validate_directive requires Land none for external and warns when external lacks Accept: user.)
