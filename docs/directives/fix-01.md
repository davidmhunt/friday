# fix-01: Landing, Verify and status rules do what the docs say
Status: done
Goal: v1-final
Node: any
Deliverable: code
Land: goal
Verify: uv run --with pytest pytest -q tests/test_final_fixes.py && uv run --with pytest pytest -q && claude plugin validate .
Hardware: none

## Goal
The lifecycle defects from the audit are gone, each proved by a test in tests/test_final_fixes.py:
a goal cannot land while any of its directives is unfinished, `Verify: none` is never run as a
shell command, the commit guard protects the goal's Base, and a blocked directive is unblocked by
a command instead of a hand edit.

## Steps
1. `friday land --goal` (bin/friday): refuse (new exit code 7, naming the ids) unless every listed
   directive is `done`, whatever its `Land:`; re-run Verify for every directive whose Verify is
   not `none`; remove the unreachable external branch.
2. `Verify: none`: `friday check` accepts it only for `Deliverable: external` (error otherwise);
   `friday verify` and the Stop gate (hooks/friday_hook.py) skip it and say so.
3. `friday check`: an empty `Hardware:` value is an error. Remove the unread `verify` config key
   from lib/friday_core.py.
4. Commit guard (hooks/friday_hook.py): while a directive is active, refuse commits on the goal's
   `Base` as well as `main`/`master`, and name the branch `friday/<goal>` in the message.
5. `friday unblock <id>`: on the goal branch, set a `blocked:` directive back to `approved` with a
   Log line, one commit; `dispatch --unblock` reuses it. When `friday finish --blocked` blocks a
   directive, set its goal to `blocked: <id>`; `unblock` sets the goal back to `running`.
6. tests/test_final_fixes.py covers steps 1 to 5; CHANGELOG entries under Unreleased.

## Out of scope
- The review gate (gate-01) and docs beyond the CHANGELOG (spec-01).
- Running Verify detached, and the 180 s git timeout.

## Log

### 2026-11-18
Commits:
- d145183 test_status_json: run the CLI with a temp HOME so the machine's node.toml cannot leak in
- eca46c1 Tests for land --goal gating; CHANGELOG entries for the fix-01 lifecycle fixes
- fe5d5d5 friday unblock <id>: blocked -> approved in one commit; finish --blocked blocks the goal; dispatch --unblock reuses it
- 221b5a3 Commit guard: refuse commits on the goal's Base as well as main/master, naming friday/<goal>
- eeff828 check: empty Hardware is an error; drop the unread verify config key from docs
- 2e36c2d Verify none: only for external; verify and the Stop gate skip it and say so
- 98aecd0 land --goal: refuse unless every directive is done (exit 7), reverify all non-none Verify
Notes:
2026-11-18: Dispatched from thinkpadP15v3 to cpsl-homebase
Verify: Verify passed: uv run --with pytest pytest -q tests/test_final_fixes.py && uv run --with pytest pytest -q && claude plugin validate .
Independent review: no gaps
