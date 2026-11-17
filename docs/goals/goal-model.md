# goal-model: One branch and one PR per goal, deliverable types, a deterministic format check
Status: running
Base: v1
Land: pr

## Goal
A goal is one `/friday:plan` run, one approval, one branch `friday/<goal>` and one PR into its
Base. Its directives are verified, independently reviewed chunks of commits on that branch:
each step that changes tracked files is one commit, and each directive adds one record commit.
Directives declare a Deliverable (code, doc, slides, external) so reports and slides go through
the same loop as code. One parser in `lib/friday_core.py` defines the goal
and directive formats; `friday check` and a PostToolUse hook enforce them.

It holds when `uv run --with pytest pytest -q && claude plugin validate . && ./bin/friday check --all`
passes on `friday/goal-model` and the six directives below are done, with one PR into `v1`.

## Directives
1. gm-01: Goal and directive formats: parser, validator, `friday check` / `friday parse`, PostToolUse hook
2. gm-02: Goal branches in the CLI: `start` on the goal branch, ordering, `land --goal`, `status`
3. gm-03: `/friday:execute` on the goal model: parse-driven Prepare, Acceptance review, land by field
4. gm-04: Planning and format docs: plan and directive skills, README, workflow, CHANGELOG, HANDOFF, bench-01 migration
5. gm-05: Lean bookkeeping in the CLI: `start` commits nothing, `finish` writes the record in one commit
6. gm-06: `/friday:execute` on lean bookkeeping, readable progress, commit rules and parallelism docs

## Log
- 2026-11-17: Planned and approved. PR #1 (fleet-01) merged into v1 first; this goal branches from
  v1 after it. Bootstrap: the current `/friday:execute` makes one PR per directive, so this goal
  is run with a session-local copy of the workflow that works on `friday/goal-model` and skips the
  per-directive PR. The repo's `workflows/execute.js` is changed only by gm-03.
- 2026-11-17: Amended with the user: gm-05 and gm-06 added after gm-04 to cut bookkeeping commits
  (start commits nothing, finish writes one record commit, measure-only steps write
  runs/<id>/notes.md) and record the parallelism decision.
