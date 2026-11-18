# Migrating a v0.20 project to friday v1

CPSL_TI_Radar is the worked example (three commits: runtime, adoption, removal).

1. **Runtime (optional).** Add `./run`, `docker/dev/` and a check script; see
   [runtime.md](runtime.md). Make the check script the default `Verify:`.
2. **Facts.** Replace `AGENTS.md` with a `CLAUDE.md` of project facts the model can't infer: how to
   run things, conventions, hardware rules, credentials. Drop the role, loop, tier and status
   sections; the plugin covers them.
3. **Config.** Add `.claude/friday.json` with `run_wrapper`, `run_only` and `hardware` patterns.
   Test each pattern against your real commands before relying on it.
4. **Specialists become skills.** A `.friday-project/roles/<role>.md` becomes
   `.claude/skills/<role>/SKILL.md`: keep the rules, drop the namespace, tier and handoff parts.
5. **Directives.** Create `docs/directives/`. Open v0.20 directives under `.friday/active/` are
   local state: re-plan the ones still wanted with `/friday:plan`.
6. **Remove v0.20.** `git rm` the `.friday` submodule, `AGENTS.md`, `harness.sh`, `.agents/`,
   `.claude/agents/`, `.friday-project/`, and the `init_harness` block in `.gitignore`.
7. **Goals.** Create `docs/goals/` (one file per goal) and give every directive a `Goal:` and a
   `Deliverable:` header line; see "Migrating a directive to a goal" below.
8. **Init and check.** Run `friday init` in the repo (allow rules in `.claude/settings.json`, the
   `commit-msg` hook), then `friday check --all` until every goal and directive passes.
9. **Install the plugin** and run one small directive end to end before relying on it.

What maps where:

| v0.20 | v1 |
|---|---|
| A directive as the unit of approval | a goal in `docs/goals/<goal>.md` listing directives |
| Controller + Planner | the session itself + `/friday:plan` |
| Coder, Runner, Reviewer | `implementer`, `runner`, `verifier` agents |
| Author, Editor, Researcher, Architect | the session, `/deep-research`, or a project skill |
| `status.md`, `log.md`, `status_history.md` | `friday status`, the directive's Log, git history |
| Claims table | hardware leases (`friday release`) |
| Spawn titles, model self-reports | agent frontmatter pins the model |
| `command_guard.py` (Antigravity only) | deny list hook, now in Claude Code |
| Rules 1, 5, 6, 9 | `data-artifacts` skill |
| Rules 7, 11, 15, 18 | `long-jobs` skill, `runner` agent |
| Rule 12 (commit attribution) | commit-trailer hook |

## Migrating a directive to a goal

A directive written before the goal model (for example `bench-01` in CPSL_TI_Radar) fails
`friday check` with two errors: missing `Goal:` and missing `Deliverable:`. Everything else in it
(Status, Node, Verify, Hardware, Goal/Steps/Out of scope/Log sections) already passes. A
one-directive goal needs:

1. Two header lines in `docs/directives/bench-01.md`, after `Status:`:

   ```
   Goal: bench-warnings
   Deliverable: code
   ```

2. A goal file `docs/goals/bench-warnings.md`:

   ```
   # bench-warnings: Silence the bench_pipeline allocator warning
   Status: approved
   Base: main
   Land: pr

   ## Goal
   A Release build of `bench_pipeline` emits no `-Wmismatched-new-delete` warning, with one PR.

   ## Directives
   1. bench-01: Silence the -Wmismatched-new-delete warning in bench_pipeline

   ## Log
   ```

Then `friday check --all` passes, `/friday:execute bench-01` works on branch `friday/bench-warnings`
and `friday land --goal bench-warnings` opens the PR. `Land:` is optional in the directive (it
defaults to `goal`).
