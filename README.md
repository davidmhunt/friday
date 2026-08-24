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
```

Then point your coding agent (Claude Code, Antigravity, or any other) at
**`setup/SETUP.md`** and say *"walk me through `.friday/setup/SETUP.md`."*
That's the preferred path — the interview needs judgment (recommending
defaults, taking real setup actions like `uv init` or creating a remote,
adapting when an answer makes a later question moot) that a bare script
can't provide. The agent conducts the interview, writes
`harness.config.env` itself, then invokes `init_harness.py` to do the
mechanical work: creates a symlink tree (`harness/`, `.claude/`,
`.agents/`) pointing into `.friday/` for everything identical across
projects, plus real materialized copies of anything needing
project-specific customization (rules docs, `AGENTS.md`, `README.md`,
`USER_GUIDE.md`, and `docker-compose.yml` if Docker is enabled).

A human can also skip the agent and either hand-write
`harness.config.env` (see `setup/harness.config.env.example`) or run the
script's own bare interactive interview directly:

```bash
python3 .friday/setup/init_harness.py             # interview if no config yet, else re-sync
python3 .friday/setup/init_harness.py --reconfigure # re-run the interview
```

Either way, re-running is idempotent and won't overwrite files you've
hand-edited beyond the interview answers.

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
