# exec-01: Workflow prompts run each friday command alone, with no `cd`, chaining or `echo $?`
Status: approved
Goal: exec-commands
Node: any
Deliverable: code
Land: goal
Verify: uv run --with pytest pytest -q tests/test_execute_prompts.py && uv run --with pytest pytest -q && claude plugin validate .
Hardware: none

## Goal
Each prompt in `workflows/execute.js` that runs a friday command tells the agent to run exactly
that command as its own Bash call from the current directory (the repo root), with no `cd`, no
`&&`, `;` or `|`, and no `echo $?`, because the Bash tool result already carries the exit code.
tests/test_execute_prompts.py proves every such prompt carries the instruction and none asks for
an echoed exit code.

## Steps
1. In `workflows/execute.js` add one constant, e.g. `ALONE`, with that instruction (name the
   reason: chained commands do not match the repo's `Bash(friday …)` allow rules), and append it
   to every prompt that runs `friday parse`, `friday start`, `friday finish` (both the record and
   the `--blocked` path), `friday land <id>` and `friday land --goal`. Where a prompt says "from the
   repo root", say that the session's current directory is the repo root, so no `cd` is needed.
   Leave the Verify prompt's own command as written (it is the directive's command, not friday's).
2. Add `tests/test_execute_prompts.py`: read `workflows/execute.js`; for every template literal
   that contains `friday parse`, `friday start`, `friday finish` or `friday land`, assert it also
   references the constant (or contains its text); assert the constant forbids `cd`, `&&`, `;`,
   `|` and `echo`; assert no prompt text asks to echo an exit code.
3. CHANGELOG entry under Unreleased/Fixed naming the symptom (a dispatched `friday land` refused
   by the classifier despite the allow rules).

## Out of scope
- Changing the allow rules or adding rules for `echo` or `cd`.
- The Verify command itself and agents' non-friday commands.

## Log
