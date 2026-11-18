# spec-01: `docs/spec.md` is the single reference, kept in step with the code by tests
Status: done
Goal: v1-final
Node: any
Deliverable: doc
Land: goal
Verify: uv run --with pytest pytest -q tests/test_docs.py tests/test_spec.py && uv run --with pytest pytest -q && claude plugin validate .
Hardware: none

## Goal
One document, `docs/spec.md`, states everything friday 1.0 does; the other docs link to it
instead of repeating it, and stale documents are gone. tests/test_spec.py fails when the spec and
the code disagree on commands, header fields, statuses, exit codes or hook rules.

## Steps
1. Write docs/spec.md from the code as it stands after gate-03 and goal review-range: the model (goal, directive,
   step); both file formats; the status lifecycle including `awaiting review` and `blocked`; who
   may change what (user approves and accepts, commands write Status and Log); pre-approved
   commands (`## Allowed commands`: read from Base, scoped to the active directive, what still
   prompts or is denied, and that dispatch, nodes --clean and release prompt unless listed); where plan amendments go (commits on
   Base, merged in by `friday start` before the next directive) and how a directive's change set
   is found (`friday commits`); every command with
   flags and exit codes; the execute workflow's phases; every hook rule with its event, including the git `commit-msg` guard friday installs and
   `--no-verify`; what is
   enforced and what is advice; `.claude/friday.json` with a full example; the fleet and dash in
   brief with links; known limits (deny list matches inside `ssh`, a hardware prompt in a
   dispatched session has nobody to answer it unless its commands are pre-approved, landing is
   GitHub PRs only, the lease is taken when the prompt is shown and expires after 4 h, Verify
   runs up to 30 minutes, friday's git calls time out after 180 s, the deny list wins over
   pre-approval so `sudo` on a robot over `ssh` stays a step the user does).
2. tests/test_spec.py: every parser subcommand and option, every header key, section name
   (including `## Allowed commands` and `## Review`) and allowed value from lib/friday_core.py, every `land`/`dispatch` exit code and every deny-list rule label
   appears in docs/spec.md; no doc mentions a `friday <sub>` or flag the parser lacks.
3. docs/workflow.md: rewrite the walkthrough for the goal model (goal branch, `land <id>` pushes,
   `land --goal` opens the PR, and when the user must run it), replace the hand edit of Status
   with `friday unblock`, complete the hooks table or link it to the spec, delete the Roadmap.
   docs/workflow.md and docs/fleet.md say how to pre-approve commands for an unattended or
   dispatched run, with an example.
4. Delete docs/HANDOFF.md (move anything still true into the spec). Fix README.md: command list,
   Status section, links to the spec. Fix the contradiction in skills/plan/SKILL.md about which
   files planning changes. agents/verifier.md: review the deliverable's files, ask for tests only
   for `code`, and do not expect `Built:`/`Link:` lines nobody writes (remove that requirement
   from skills/directive/SKILL.md).
5. Add a CLAUDE.md for this repo, under 60 lines: how to run the tests, that edits must not be
   made in the checkout loaded as the plugin, the default Verify, where the spec is.

## Acceptance
- docs/spec.md has a section for each of: model, formats, lifecycle, commands, workflow, hooks, enforced versus advice, project config, known limits.
- Every command in `friday --help` has an entry in the spec with its exit codes.
- docs/HANDOFF.md is gone and nothing links to it; no doc names `friday dispatch <id>`, `status --html` or a Roadmap of built work.
- A reader can tell from the spec alone when a goal's PR opens by itself and when they must run `friday land --goal`.
- CLAUDE.md exists and is under 60 lines.
- A reader can tell from the spec where to amend a running goal's plan and when the running session sees the change.
- A reader can tell from the spec, docs/workflow.md or docs/fleet.md how to pre-approve a command for a directive, where the list is read from, and what still prompts or is denied.

## Out of scope
- The tutorial and recipes (spec-02); the version bump (rel-01).

## Log

### 2026-11-18
Commits:
- 3381fb4 Amend spec-01 and spec-02: document pre-approved commands (gate-03), as the user asked
- 6a35439 spec-01 step 1: docs/spec.md, the single reference
- 2dc7bfe spec-01 step 2: tests/test_spec.py keeps docs/spec.md in step with the parser, headers, exit codes and deny list
- d5fd6c6 spec-01 step 3: workflow.md rewritten for the goal model, unblock, hooks, pre-approval; fleet.md pre-approval
- c50b030 spec-01 step 4: HANDOFF deleted, README command list and Status, plan and verifier fixes, Built/Link lines dropped
- 57ca526 spec-01 step 5: CLAUDE.md for this repo
- 2399a21 spec-01: land --goal behaviour matches execute.js; CLAUDE.md file pointers and start/Status wording
Notes:
2026-11-18: Dispatched from thinkpadP15v3 to cpsl-homebase
Verify: Verify passed: uv run --with pytest pytest -q tests/test_docs.py tests/test_spec.py && uv run --with pytest pytest -q && claude plugin validate .
Independent review: gaps fixed in second review: 1. /home/david/Documents/claude_temp/friday.friday/v1-final/docs/spec.md lines 374-376 and 384-386 (same claim in docs/workflow.md walkthrough step 5): The spec says the workflow runs 'friday land --goal' only when no directive of the goal is 'awaiting review', and that the goal PR opens by itself only when every directive is 'Accept: auto'. The code works differently. workflows/execute.js skips 'land --goal' only when the current directive is 'Accept: user'. It never checks earlier directives. So if an earlier 'Accept: user' directive was accepted before the last directive finishes, the goal PR does open by itself, which the spec says cannot happen. If the earlier one is still pending, the workflow runs 'land --goal' and it exits 7. The reader's actions still come out right: running 'land --goal' again is harmless, and the spec covers exit 7. But this is a factual error in the section that answers the 'when does the PR open by itself' acceptance bullet. (evidence: workflows/execute.js:296-305: 'if (awaiting) {...return}' where 'awaiting = d.accept === 'user'' (line 273) refers only to the current directive. Then 'if (!isLast) return', then it runs 'friday land --goal' unconditionally. Nothing reads the other directives' statuses.) 2. /home/david/Documents/claude_temp/friday.friday/v1-final/CLAUDE.md line 9: CLAUDE.md says 'lib/friday_core.py' holds the 'parser, header fields, statuses, exit codes, deny list'. The deny list and the exit codes are not there, so a future agent following CLAUDE.md will look in the wrong file. A smaller inaccuracy in the same file: line 34 says 'friday start' writes a directive's Status, but per the spec 'start' commits nothing to the directive. (evidence: 'DENY = [' is at hooks/friday_hook.py:28, 'DISPATCH_EXIT' is in bin/friday:1133 and 'PREPARE_EXIT' is in lib/friday_fleet.py:299. grep finds none of the three in lib/friday_core.py.)
