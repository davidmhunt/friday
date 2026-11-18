# exec-02: `/friday:execute` merges Base before it parses, so amendments and new directives are seen (fixes #18)
Status: approved
Goal: field-fixes
Node: any
Deliverable: code
Land: goal
Verify: uv run --with pytest pytest -q tests/test_execute_prompts.py tests/test_execute_order.py && uv run --with pytest pytest -q && claude plugin validate .
Hardware: none

## Goal
The execute workflow reads the directive only after `friday start` has merged Base into the goal
branch, so a directive added or amended on Base runs from its current text. A resumed workflow
(`resumeFromRunId`) re-parses whenever the goal branch moved, instead of replaying a stale cached
parse. tests/test_execute_order.py and tests/test_execute_prompts.py prove it.

## Steps
1. workflows/execute.js Prepare: run the start step first (`friday start <id> --no-gate`, which
   merges Base), and have it also return `git rev-parse HEAD` after the merge; then run
   `friday parse <id> --json`, with that sha written into the parse prompt so a cached parse is
   reused only when HEAD is unchanged. If start refuses, stop as today. If parse then fails, run
   `friday finish <id> --blocked "<parse errors>"` so the marker is cleared and the directive says
   why, and stop.
2. Anything the start step needed from parse (none expected: start takes only the id) is moved
   or re-derived; the phases' detail text in `meta` names the new order.
3. tests/test_execute_order.py: in the workflow source, the start prompt is issued before the parse
   prompt; the parse prompt interpolates the start step's sha; a parse failure leads to a
   `friday finish --blocked` prompt. A CLI-level test: a directive committed only on Base is
   parsed successfully after `friday start` on a goal branch that lacked it, and an amended step
   shows its new text. CHANGELOG in the 1.1.0 section (Fixed) naming #18.

## Out of scope
- `friday parse` reading from `origin/<Base>` directly (start's merge already brings it in).

## Log
