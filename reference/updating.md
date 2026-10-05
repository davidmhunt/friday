# Keeping the harness updated

Pulling harness updates into a project, plus the v0.17 to v0.18 and pre-v0.13 migration steps. Back to the [User Guide](../USER_GUIDE.md).

The harness itself (`.friday/`) evolves — new hooks, rule fixes, template
changes. Pulling those updates into a project you're already operating is
a separate, short operation from day-to-day use:

```bash
./harness.sh sync pull   # pulls the latest .friday/ commit, re-syncs, bumps the pointer
```

This project's symlinked files (roles, generic rules, adapters, hooks,
tools, this guide) update the moment `.friday/` moves to a newer commit —
no render step. Materialized files (`harness.md`, `docker/Dockerfile`,
`AGENTS.md`, `README.md`, and a few others) don't auto-update, since
they're real per-project copies that may carry hand-edits; `init_harness.py`
reports which ones differ from a fresh render without overwriting them,
and you opt in per-file with `--force-materialize=<path>` when you want a
friday-side template change to actually land.

This is the operator-facing summary. For the full story — installing
`harness.sh` for the first time, pushing a local `.friday/` edit upstream
so other projects can pull it, and the plain-git-submodule sequence behind
the wrapper — see friday's own `README.md`, which is the installer doc;
this guide is the day-to-day operator doc, and deliberately doesn't
duplicate that material.

### Upgrading from v0.17 or earlier to v0.18.0 (lead mode)

The symlinked
role docs, rules, adapters and hooks switch to lead mode on the pull itself.
The materialized files that changed shape do not — re-render them (after
saving any hand-edits you want to carry over):

```bash
python3 .friday/setup/init_harness.py --dry-run   # lists SKIP / REFUSE / RETIRED lines
python3 .friday/setup/init_harness.py \
  --force-materialize=.friday/active/harness/harness.md \
  --force-materialize=.friday/active/harness/roles/reviewer.md \
  --force-materialize=.friday/active/harness/roles/researcher.md \
  --force-materialize=.friday/active/harness/roles/author.md \
  --force-materialize=.friday/active/harness/rules/task_tracking.md \
  --force-materialize=.friday/active/harness/rules/version_control.md \
  --force-materialize=.friday/active/harness/rules/environment.md \
  --force-materialize=.friday/active/harness/plans/history.md \
  --force-materialize=.friday/active/harness/templates/research_memo_template.md
```

(add `docs/references/needs_pdf.md` if you use the bibliography tools, and
the `.agents/agents/*.md` paths if you use Antigravity; then re-apply any
project facts you had written into `version_control.md`/`environment.md`).
`status.md`, `status_history.md` and `plans/goals.md` hold live state:
restructure them by hand to the new skeleton (Loops / Directives / Claims
tables; Objectives / Standing context / Specs; a new `status_history.md`
header) rather than force-rendering over them. `AGENTS.md` is project-owned
— port the new Multi-Agent Workflow section, Project facts rows and index
row by hand. Files listed under `=== Retired files ===` (`plans/next_steps.md`,
`suggestions.md`, `long_term.md`, `coding/`) are no longer read by any
role: carry anything still open into directives, archive, delete. A
`REFUSE` line means a real file sits where a symlink belongs — usually a
local override; diff it against the new template, keep what is genuinely
project-specific (a project specialist goes to `.friday-project/roles/`,
[User Guide, Roles and tiers](../USER_GUIDE.md#roles-and-tiers)), then delete the file and re-run. Full notes: `CHANGELOG.md`, v0.18.0.

### Migrating a project set up before v0.13.0

Before that release, the harness generated an entire `harness/` tree at the consumer repo root,
tracked by this project's own git history; v0.13.0 relocated all of that
into `.friday/active/harness/`. A project upgrading past that boundary
needs to drop the now-orphaned `harness/**` paths from its own index —
`--untrack-legacy` does that:

```bash
python3 .friday/setup/init_harness.py --untrack-legacy
```

It intersects `git ls-files` with `MANIFEST.json`'s `legacy_dests` (a
frozen snapshot of every `harness/…` dest that existed pre-v0.13.0) and
runs `git rm --cached` on exactly what's still tracked there — an explicit
file list, never a glob, never `-r`, never a commit, and safe to run more
than once. It's the counterpart to `--untrack-harness` (which handles what
*stays* at the repo root but should stop being tracked, e.g. `.claude/`,
`.agents/`): `--untrack-legacy` handles what *moved out* of the project
entirely.

Because it's manifest-derived, it can only reach files the manifest
actually generated — it structurally cannot know about content a project
added on top of the harness's own output. Two things from the old
`harness/` tree need handling by hand: research memos, which moved to
`docs/research/` in the same release (`git mv harness/research/*.md
docs/research/` preserves their history — a plain untrack + re-add would
lose it), and `harness/running/logs/.gitkeep` — a placeholder git needs to
track an otherwise-empty directory, never itself a manifest entry — which
needs its own `git rm --cached harness/running/logs/.gitkeep`.
