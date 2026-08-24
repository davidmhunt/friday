# friday

A portable multi-agent development harness — role contracts (Planner,
Coder, Controller, Runner, Reviewer, Author, Researcher), a shared loop and
rule set, adapters for Claude Code and Antigravity, hook-based guardrails,
and a Docker dev-container setup. Drop it into a project as a git
submodule, run the setup interview once, and get a working harness without
re-authoring it.

The full operator manual — how the Planner → Controller → Reviewer loop
works, where status lives, how to feed the agents inputs, and the complete
Docker container workflow — is `USER_GUIDE.md` in this repo. It's the same
file for every project (symlinked in as `harness/USER_GUIDE.md`, never
templated), so read it here or in any consumer project.

## Getting started in a new project

1. **Add the submodule** at the consumer project's repo root:
   ```bash
   git submodule add https://github.com/davidmhunt/friday.git .friday
   git submodule update --init --recursive
   ```
2. **Run the setup interview.** Point your coding agent (Claude Code,
   Antigravity, or any other) at `.friday/setup/SETUP.md` and say *"walk me
   through `.friday/setup/SETUP.md`."* That's the preferred path — the
   interview needs judgment (recommending defaults, taking real setup
   actions like `uv init` or creating a remote, adapting when an answer
   makes a later question moot) that a bare script can't provide. The agent
   asks about project identity, repository layout, how code runs, GPU/
   accelerator hardware, background jobs, version control & task tracking,
   agent tooling, Docker, and bibliography tooling — one topic at a time —
   then writes `harness.config.env` itself and runs `init_harness.py`.
3. **What that leaves you with**: a symlink tree (`harness/`, `.claude/`,
   `.agents/`) pointing into `.friday/` for everything identical across
   every project, plus real materialized copies of anything needing
   project-specific customization (the three project-facing rules docs,
   `AGENTS.md`, `README.md`, and `docker-compose.yml` if Docker is
   enabled). `AGENTS.md` is the one file every agent session loads first —
   it's where this project's own facts (name, working root, results doc,
   package manager, task tracker, repository layout) live.
4. **Start working**: tell an agent "you are the planner agent" to open the
   first cycle. See `USER_GUIDE.md` for the full workflow.

A human can also skip the agent and either hand-write `harness.config.env`
(see `setup/harness.config.env.example`) or run the script's own bare
interactive interview directly:

```bash
python3 .friday/setup/init_harness.py              # interview if no config yet, else re-sync
python3 .friday/setup/init_harness.py --reconfigure  # re-run the interview
```

Either way, re-running is idempotent and won't overwrite files you've
hand-edited beyond the interview answers — it warns and tells you to pass
`--force-materialize=<path>` if you want a fresh render instead.

## Reconfiguring later

Nothing from the interview is one-shot. Switched package managers, added a
task tracker, provisioned a GPU, want Docker now — re-open
`.friday/setup/SETUP.md` with an agent (or run `init_harness.py
--reconfigure`) any time. It treats your existing `harness.config.env` as
defaults and only asks about what's actually changing.

## Updating the harness in a project that already has it

The symlinked files (roles, generic rules, adapters, hooks, tools,
`USER_GUIDE.md`) update automatically the moment a consumer project's
`.friday/` checkout moves to a newer commit — there's no re-render step for
those. The materialized files (`harness.md`, the project-facing rules
docs, `AGENTS.md`, `README.md`, `docker-compose.yml`) don't auto-update —
they're real per-project copies that may carry hand-edits, so a friday-side
template change needs an explicit `--force-materialize` to land.

**Pull the latest friday commit into one project:**

```bash
git submodule update --remote --merge .friday
python3 .friday/setup/init_harness.py       # re-syncs symlinks; reports which
                                             # materialized files differ from a
                                             # fresh render, without overwriting
git add .friday
git commit -m "Bump .friday to <version>"
```

Add `--force-materialize=<path>` (repeatable) to actually pick up a changed
`.tmpl` file's new content in one of the materialized files listed above.

**Convenience wrapper** (`setup/harness_sync.sh`) automates the same steps
for both directions — pushing a local `.friday/` edit upstream, or pulling
an upstream change down:

```bash
./harness.sh sync push   # from a project with local .friday/ edits:
                          # commits+pushes them upstream, bumps the pointer here
./harness.sh sync pull   # pulls the latest .friday/ commit, re-syncs, bumps the pointer
```

`harness.sh` is a thin project-owned wrapper around
`.friday/setup/harness_sync.sh` (kept outside `.friday/` itself since it's
the one entry point a project's own shell history/aliases would reference).
Add it once, per project:

```bash
printf '#!/usr/bin/env bash\nexec "$(dirname "$0")/.friday/setup/harness_sync.sh" "$@"\n' > harness.sh
chmod +x harness.sh
```

## Porting a local harness change to every project that uses it

Made a fix directly inside a consumer project's `.friday/` checkout (e.g.
editing a symlinked hook)? That edit physically lands in the submodule's
working tree, not the consumer project. Push it upstream, then pull it into
every other project:

```bash
./harness.sh sync push   # from the project where you made the edit
./harness.sh sync pull   # from every other project that should get it
```

Without the wrapper, the plain git submodule sequence is: commit + push
inside `.friday/`, then commit the updated submodule pointer (gitlink) in
the consumer repo — repeat the pull half in each other project.

## Repo layout

See `MANIFEST.json` for exactly which files are shared symlinks vs.
per-project templates, and `USER_GUIDE.md` for the full operator manual.
