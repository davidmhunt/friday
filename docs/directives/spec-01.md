# spec-01: `docs/spec.md` is the single reference, kept in step with the code by tests
Status: approved
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
1. Write docs/spec.md from the code as it stands after gate-03: the model (goal, directive,
   step); both file formats; the status lifecycle including `awaiting review` and `blocked`; who
   may change what (user approves and accepts, commands write Status and Log); pre-approved
   commands (`## Allowed commands`: read from Base, scoped to the active directive, what still
   prompts or is denied, and that dispatch, nodes --clean and release prompt unless listed); every command with
   flags and exit codes; the execute workflow's phases; every hook rule with its event; what is
   enforced and what is advice; `.claude/friday.json` with a full example; the fleet and dash in
   brief with links; known limits (deny list matches inside `ssh`, a hardware prompt in a
   dispatched session has nobody to answer it unless its commands are pre-approved, landing is
   GitHub PRs only, the lease is taken when the prompt is shown and expires after 4 h, Verify
   runs up to 30 minutes).
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
- A reader can tell from the spec, docs/workflow.md or docs/fleet.md how to pre-approve a command for a directive, where the list is read from, and what still prompts or is denied.

## Out of scope
- The tutorial and recipes (spec-02); the version bump (rel-01).

## Log
