# cli-03: `friday init` adds the friday allow rules to a repo; dispatch refuses a repo without them
Status: approved
Goal: cli-ergonomics
Node: any
Deliverable: code
Land: goal
Verify: uv run --with pytest pytest -q tests/test_init.py tests/test_dispatch.py && uv run --with pytest pytest -q && claude plugin validate .
Hardware: none

## Goal
Every repo that friday runs in allows its lifecycle commands deterministically, so unattended
sessions are not stopped by the auto-mode classifier on `friday start` or `friday land`:
`friday init` merges the friday allow rules into the repo's tracked `.claude/settings.json`, the
plan skill runs it in a repo that lacks them, and `friday dispatch` refuses a goal whose source
ref's `.claude/settings.json` does not allow them. tests/test_init.py proves the merge and the refusal.

## Steps
1. Define the rule list once in `lib/friday_core.py` (`FRIDAY_ALLOW`: `friday status`,
   `status *`, `new *`, `check *`, `parse *`, `start *`, `verify`, `verify *`, `finish *`, `land *`,
   each as `Bash(...)`), matching this repo's `.claude/settings.json`.
2. Add `friday init`: create or merge `.claude/settings.json` at the repo root so
   `permissions.allow` contains every `FRIDAY_ALLOW` rule, keeping all other keys and rules and
   their order; print what it added or that nothing was missing; never touch
   `settings.local.json`; refuse an unparsable file with its path. It does not commit.
3. `friday dispatch`: read `.claude/settings.json` from the goal's source ref (`git show`); refuse
   (own exit code, fix `friday init`, then commit and push) when any `FRIDAY_ALLOW` rule is missing.
4. `skills/plan/SKILL.md`: before committing a plan in a repo, run `friday init` and include the
   settings file in the plan commit when it changed. README and docs/fleet.md explain why the rules
   live in the repo (a plugin cannot grant permissions). CHANGELOG entry.
5. Add `tests/test_init.py`: create from nothing, merge into existing rules and keys, idempotent
   re-run, unparsable refusal, this repo's own file equals `FRIDAY_ALLOW`; in tests/test_dispatch.py
   a source ref without the rules is refused and one with them passes.

## Out of scope
- Allow rules for anything beyond friday's own commands (raw git push, gh merge stay with the classifier).
- Editing user or node-level settings.

## Log
