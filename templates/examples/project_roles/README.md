# Project-specific specialist roles

The core team (Controller, Planner, Architect, Coder, Runner, Researcher,
Author, Editor, Reviewer) covers most projects. When a project has a domain
the core roles shouldn't own — board design, a firmware toolchain, a
licensed CAD tool — it adds its own specialist. Nothing here is installed
automatically; copy what you need.

## What a project role is made of

All of these live in the **project's own repo and are tracked there** —
`init_harness.py` never writes, overwrites, or git-excludes them.

| File (in the consumer repo) | What | Example to copy |
|---|---|---|
| `.friday-project/roles/<role>.md` | The role doc: role, tier, namespace, constraints, handoff. **Its presence is the registration.** | `hardware/role.md` |
| `.claude/agents/<role>.md` | Claude Code adapter (frontmatter: description, model, tools) | `hardware/claude/hardware.md` |
| `.agents/agents/<role>.md`, `<role>-heavy.md` | Antigravity adapters (mid tier + `[heavy]` escalation file) | `hardware/antigravity/` |
| a facts doc the role reads, e.g. `hardware/README.md` | Project facts (boards, owners, tools) — keeps the role doc generic | `hardware/facts_README.md` |

Role names are lowercase (`[a-z][a-z0-9_]*`) and must not collide with a
core role.

## What registration buys you

On every `init_harness.py` run, each `.friday-project/roles/<role>.md` is
symlinked to `.friday/active/harness/roles/<role>.md`, so agents find it
beside the core role files. The hooks discover the same directory at run
time:

- `check_agent_spawn.py` enforces the `<role>(model): task` spawn title and
  treats `<role>-heavy` as its high-tier variant;
- `check_commit_msg.py` accepts `<Role>:` as a commit prefix and requires
  the directive/tracker body, like any producing role.

`init_harness.py` warns when an enabled adapter file is missing, or when an
adapter file is git-ignored (it is project content and should be tracked).

## Then tell the team

Add the role to `AGENTS.md`'s **Project specialists** row (and an index row
for its facts doc). The core docs — `harness.md`, the Controller and Planner
role files — already describe "project specialists" generically and point
there. Tier: mid by default, `[heavy]` → high, like every specialist.
