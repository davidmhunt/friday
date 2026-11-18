# fix-02: Every command and flag is real, documented in `--help` and allowed without a prompt
Status: blocked: review gaps remain: commit 3381fb4 (docs/directives/spec-01.md, docs/directives/spec-02.md): The earlier gap is still open, because HEAD has not moved. The only commit in the review range 11db7fc..HEAD is 3381fb4. Its message has no 'Directive: fix-02' line, so it fails the required commit-message check. It is also not fix-02 work: it rewrites the Steps and Acceptance of two other directives (spec-01 and spec-02) to cover gate-03 pre-approved commands, which is outside fix-02's scope (CLI surface, allow rules, help text, registry). fix-02's own commits (f21c7a7..f5932be, 4858379 and 11db7fc) are all before the review base, so this range holds no fix-02 work to review. Retagging the commit as fix-02 would be wrong. The fix is to review 3381fb4 under spec-01/spec-02 and to review fix-02 against a base before f21c7a7, or to record fix-02's review against its earlier range.
Goal: v1-final
Node: any
Deliverable: code
Land: goal
Verify: uv run --with pytest pytest -q tests/test_cli_surface.py && uv run --with pytest pytest -q && claude plugin validate .
Hardware: none

## Goal
The CLI surface is consistent: `friday --help` lists every subcommand and flag the parser accepts
(a test compares them), the flags the docs name exist, and the friday commands that skills and
dispatched sessions run match the allow rules `friday init` writes.

## Steps
1. `friday status --node NAME` (with `--json`/`--push`): passes the name to `collect`, first in
   the identity order docs/fleet.md already states.
2. `friday nodes --check`: report the number of `friday-*` tmux sessions per node, as
   docs/fleet.md says.
3. Help text (bin/friday docstring): add `init`, `session-end`, `unblock`,
   `dispatch --resume/--unblock`, `status --node`; correct the "on PATH" line to name
   `friday install`.
4. Allow rules (`FRIDAY_ALLOW` in lib/friday_core.py, .claude/settings.json): add `friday init`
   and `friday session-end`. Never add `friday accept`. The status, nodes, dispatch and clean
   skills call plain `friday ...` so the rules match, and say to run `friday install` if it is
   not on PATH.
5. Registry: add the `tailnet` key to nodes.example.toml and the key table in docs/fleet.md.
   `friday dash up` mounts the registry file the CLI actually resolved (plugin root or
   `~/.config/friday/nodes.toml`) and fails clearly when there is none.
6. tests/test_cli_surface.py: every parser subcommand and option string appears in the help text;
   every `friday <sub>` in skills/ and workflows/execute.js matches an allow rule, except
   `friday dispatch --goal <g>`, `friday nodes --clean <node>` and `friday release <resource>`,
   which stay prompted on purpose (they act on other machines or free hardware; amended by the
   user 2026-11-18) and are named in the test's `prompted()` list; steps 1, 2, 5.
   CHANGELOG entries.

## Out of scope
- New commands other than `status --node` (accept, result and unblock belong to other directives).

## Log

### 2026-11-18
Commits:
- f5932be fix-02: allow read-only nodes and dry-runs; surface test exempts only the real dispatch/clean runs
- 5a4db14 fix-02 step 6: CLI surface test (help vs parser, allow rules vs skills/workflow) and CHANGELOG
- 097f677 fix-02 step 5: update dash docker tests for the resolved registry mount
- 2b91d9b fix-02 step 5: tailnet key in registry docs; friday dash up mounts the resolved registry file
- 9d31758 fix-02 step 4: allow friday init and session-end; skills call plain friday and point to friday install
- 721ed1e friday docstring: add init, session-end, unblock, dispatch --resume/--unblock, status --node; name friday install
- e94da8a friday nodes --check: report the number of friday-* tmux sessions per node
- f21c7a7 friday status --node NAME: pass the name to collect for --json and --push
Notes:
2026-11-18: Step 6 amended by the user: dispatch, nodes --clean and release stay prompted; pre-approval moves to gate-03.
2026-11-18: Dispatched from thinkpadP15v3 to cpsl-homebase
Verify: Verify passed: uv run --with pytest pytest -q tests/test_cli_surface.py && uv run --with pytest pytest -q && claude plugin validate .
Independent review: not recorded
Blocked: review gaps remain: tests/test_cli_surface.py:19-25 (prompted()) and :115; lib/friday_core.py:33-40; skills/dispatch/SKILL.md:16, skills/clean/SKILL.md:16, skills/hardware/SKILL.md:14; docs/directives/fix-02.md Step 6 and Log: This is narrower than before but still open. f5932be adds allow rules for 'friday nodes', 'nodes --check', 'nodes --clean * --dry-run' and 'dispatch --goal * --dry-run', so the read-only nodes skill and both dry-runs no longer prompt. But the skills still run the real 'friday dispatch --goal <goal>' and 'friday nodes --clean <node>', and the hardware skill names 'friday release <resource>'. None of these matches a rule in FRIDAY_ALLOW or .claude/settings.json. The test still lets them through with the 'prompted()' exemption. Step 6 says every 'friday <sub>' in skills/ must match an allow rule, and the Goal says the commands skills run match the rules 'friday init' writes. Leaving these to prompt is a reasonable safety choice, since the user has already confirmed. But it departs from the stated requirement, and the record is only in the CHANGELOG and a code comment. The directive's Step 6 was not amended, and its Log section is empty.

### 2026-11-18
Unblocked: was blocked: review gaps remain: tests/test_cli_surface.py:19-25 (prompted()) and :115; lib/friday_core.py:33-40; skills/dispatch/SKILL.md:16, skills/clean/SKILL.md:16, skills/hardware/SKILL.md:14; docs/directives/fix-02.md Step 6 and Log: This is narrower than before but still open. f5932be adds allow rules for 'friday nodes', 'nodes --check', 'nodes --clean * --dry-run' and 'dispatch --goal * --dry-run', so the read-only nodes skill and both dry-runs no longer prompt. But the skills still run the real 'friday dispatch --goal <goal>' and 'friday nodes --clean <node>', and the hardware skill names 'friday release <resource>'. None of these matches a rule in FRIDAY_ALLOW or .claude/settings.json. The test still lets them through with the 'prompted()' exemption. Step 6 says every 'friday <sub>' in skills/ must match an allow rule, and the Goal says the commands skills run match the rules 'friday init' writes. Leaving these to prompt is a reasonable safety choice, since the user has already confirmed. But it departs from the stated requirement, and the record is only in the CHANGELOG and a code comment. The directive's Step 6 was not amended, and its Log section is empty.

### 2026-11-18
Commits:
- 3381fb4 Amend spec-01 and spec-02: document pre-approved commands (gate-03), as the user asked
Notes:
2026-11-18: Dispatched from thinkpadP15v3 to cpsl-homebase
2026-11-18: Dispatched from thinkpadP15v3 to cpsl-homebase
step 1: already implemented in f21c7a7; focused tests re-run, passing.
step 2: already implemented in e94da8a (bin/friday check_node reports N friday-* sessions per node); no change needed; focused tests pass.
step 3: already satisfied by 721ed1e; verified help text and test_cli_surface pass; no change
Verify: Verify passed: uv run --with pytest pytest -q tests/test_cli_surface.py && uv run --with pytest pytest -q && claude plugin validate .
Independent review: not recorded
Blocked: review gaps remain: commit 3381fb4 (docs/directives/spec-01.md, docs/directives/spec-02.md): The earlier gap is still open, because HEAD has not moved. The only commit in the review range 11db7fc..HEAD is 3381fb4. Its message has no 'Directive: fix-02' line, so it fails the required commit-message check. It is also not fix-02 work: it rewrites the Steps and Acceptance of two other directives (spec-01 and spec-02) to cover gate-03 pre-approved commands, which is outside fix-02's scope (CLI surface, allow rules, help text, registry). fix-02's own commits (f21c7a7..f5932be, 4858379 and 11db7fc) are all before the review base, so this range holds no fix-02 work to review. Retagging the commit as fix-02 would be wrong. The fix is to review 3381fb4 under spec-01/spec-02 and to review fix-02 against a base before f21c7a7, or to record fix-02's review against its earlier range.
