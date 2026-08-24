# friday

A portable multi-agent development harness — role contracts (Planner,
Coder, Controller, Runner, Reviewer, Author, Researcher), a shared loop and
rule set, adapters for Claude Code and Antigravity, hook-based guardrails,
and a Docker dev-container setup. Drop it into a project as a git
submodule, run the setup interview once, and get a working harness without
re-authoring it.

## Using this in a project

```bash
git submodule add <this-repo-url> .friday
git submodule update --init --recursive
python3 .friday/setup/init_harness.py
```

The interview writes `harness.config.env` at your repo root and creates a
symlink tree (`harness/`, `.claude/`, `.agents/`) pointing into `.friday/`
for everything that's identical across projects, plus real materialized
copies of anything that needs project-specific customization (rules docs,
`AGENTS.md`, `README.md`, `USER_GUIDE.md`).

Re-run it any time — it's idempotent and won't overwrite files you've
hand-edited beyond the interview answers:

```bash
python3 .friday/setup/init_harness.py             # re-sync
python3 .friday/setup/init_harness.py --reconfigure # re-run the interview
```

## Porting a change between projects

```bash
./harness.sh sync push   # from a project with local .friday/ edits
./harness.sh sync pull   # from a project that wants those edits
```

(`harness.sh` is a thin project-owned wrapper around `.friday/setup/harness_sync.sh`
— see a project's `harness/USER_GUIDE.md` for the exact one-liner to add it.)

See `harness/USER_GUIDE.md.tmpl` (materializes to `harness/USER_GUIDE.md` in
a consumer project) for the full operator manual, and `MANIFEST.json` for
exactly which files are shared symlinks vs. per-project templates.
