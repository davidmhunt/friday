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
7. **Install the plugin** and run one small directive end to end before relying on it.

What maps where:

| v0.20 | v1 |
|---|---|
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
