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

**Doc split**: this `README.md` covers installing, updating, and porting
friday itself (installer + maintainer concerns). `harness/USER_GUIDE.md`
covers operating an already-installed harness day to day (the operator
manual). If you're looking for how to *use* the harness rather than set
it up, go there instead.

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
   accelerator hardware, version control & task tracking, agent tooling,
   Docker, background jobs, bibliography tooling, and the LaTeX/Beamer
   drafting suite — one topic at a time — then writes `harness.config.env`
   itself and runs `init_harness.py`.
3. **What that leaves you with**: a symlink tree (`harness/`, `.claude/`,
   `.agents/`) pointing into `.friday/` for everything identical across
   every project, plus real materialized copies of anything needing
   project-specific customization (`harness.md`, the three project-facing
   rules docs, the Researcher/Author/Reviewer role contracts, `AGENTS.md`,
   `README.md`, and — if Docker/accelerators are enabled —
   `docker-compose.yml`, `Dockerfile`, `docker/entrypoint.sh`, and
   `gpu.md`) — plus a starter `docs/` and `harness/{coding,plans}/`
   scaffold (empty working-state files with the right headers, `docs/
   references/` with its inbox + `needs_pdf.md`, and `docs/theory/`/`docs/
   report/` if the LaTeX suite is on), the three core state files
   `harness/status.md`, `harness/status_history.md`, and `harness/log.md`
   (seeded empty and ready to use — previously referenced everywhere in the
   harness but never actually materialized), and `harness/running/logs/`
   — so every project starts from the same shape instead of inventing it on
   first use. `init_harness.py` also applies the `.gitignore`/
   `.gitattributes` fragments (secrets, gitignored directive files, and
   LaTeX/reference artifacts when those axes are enabled), appending only
   the lines a project's existing files are missing. `AGENTS.md` is the one
   file every agent session loads first — it's where this project's own
   facts (name, working root, results doc, package manager, task tracker,
   repository layout) live.
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

## What's symlinked vs. materialized in a consumer project

`MANIFEST.json` is the single source of truth for this — every path below
is a literal `dest` entry there, and `sync_symlinks()` /
`materialize_files()` in `setup/init_harness.py` are what actually create
them. This section is a human-readable rendering of that manifest, grouped
by directory; if the two ever disagree, `MANIFEST.json` is authoritative.

### Symlinked (shared — edit in `.friday/`, every project sees it next pull)

These files are byte-identical across every project by design. Their
symlinks all point back into this repo's checkout at `.friday/`; nothing
about them is ever rendered or project-specific.

| Consumer path | Points into `.friday/` | Notes |
|---|---|---|
| `harness/USER_GUIDE.md` | `USER_GUIDE.md` | the operator manual you're reading a copy of right now |
| `harness/roles/{coder,controller,planner,runner}.md` | `harness/roles/` | 4 of the 7 role contracts, always present — an unused role is inert (only read when a session is assigned that role), so there's no pruning step |
| `harness/rules/{conventions,md_hygiene,monitoring,checkpoint_compat,data_artifacts}.md` | `harness/rules/` | the 5 rules docs with zero project-specific content |
| `harness/plans/directives/TEMPLATE.md` | `harness/plans/directives/` | the directive template every real directive is copied from |
| `harness/research/README.md`, `harness/review/README.md`, `harness/running/README.md` | same paths | namespace explainers for the Researcher/Reviewer/Runner working directories — zero project-specific content |
| `docs/references/inbox/README.md` | `docs/references/inbox/` | explains the drop-a-PDF-here + `intake_references.py` workflow |
| `harness/tools/{_config,intake_references,verify_references,check_unavailable_sources,lint_research_memo,find_open_access_pdf}.py` | `harness/tools/` | bibliography-workflow tools; config-driven via `harness.config.env` (see `harness/tools/_config.py`), not templated |
| `.claude/agents/{author,coder,controller,planner,researcher,reviewer,runner}.md` | `adapters/claude/agents/` | Claude Code role adapter files — present only if `ADAPTERS_ENABLED` includes `claude` |
| `.claude/hooks/{check_agent_spawn,check_md_hygiene,check_commit_msg,command_guard}.py`, `.claude/hooks/{pre-commit,commit-msg,README.md}` | `adapters/hooks/` | same physical files as `.agents/hooks/*` below — one canonical implementation, two symlink targets |
| `.agents/agents/{author,coder,coder-heavy,controller,planner,planner-heavy,researcher,researcher-heavy,researcher-quick,reviewer,reviewer-heavy,runner,runner-judgment}.md` | `adapters/antigravity/agents/` | Antigravity role + tier-variant adapter files — present only if `ADAPTERS_ENABLED` includes `antigravity` |
| `.agents/hooks/{check_agent_spawn,check_md_hygiene,check_commit_msg,command_guard}.py`, `.agents/hooks/{pre-commit,commit-msg,README.md}` | `adapters/hooks/` | same canonical files as the `.claude/hooks/*` row above |
| `.dockerignore` | `docker/` | only present if `DOCKER_ENABLED=true` — the only Docker file that's still a plain symlink; `Dockerfile`, `docker/entrypoint.sh` and `docker/antigravity_settings.json` are materialized (see below) since they now render per-project |
| `.git/hooks/{pre-commit,commit-msg}` | *(anchored to `.claude/hooks/`, per `MANIFEST.json`'s `git_hooks` key — not a manifest `symlinks` entry)* | a second-order symlink: `.git/hooks/*` → `.claude/hooks/*` → `.friday/adapters/hooks/*`; installed by `install_git_hooks()` |

### Materialized (real per-project copies, rendered once)

These start life as a `.tmpl` file in `.friday/`, get their `[SET AT
SETUP: ...]` tokens substituted and inapplicable `<!-- SECTION -->` blocks
dropped by `render()`, and are written as ordinary files in the consumer
project — safe to hand-edit afterward. `init_harness.py` never overwrites
one that already exists and differs from a fresh render; use
`--force-materialize=<path>` to force a re-render.

| Consumer path | Template source in `.friday/` | Gated by |
|---|---|---|
| `harness/harness.md` | `harness/harness.md.tmpl` | — |
| `harness/roles/researcher.md` | `harness/roles/researcher.md.tmpl` | `LATEX_DRAFTING_ENABLED` toggles the `docs/theory/` namespace text |
| `harness/roles/author.md` | `harness/roles/author.md.tmpl` | `LATEX_DRAFTING_ENABLED` toggles the `docs/report/` namespace + Slide decks section |
| `harness/roles/reviewer.md` | `harness/roles/reviewer.md.tmpl` | `LATEX_DRAFTING_ENABLED` toggles the theory/report clause in the citation-check step |
| `harness/rules/environment.md` | `harness/rules/environment.md.tmpl` | — |
| `harness/rules/task_tracking.md` | `harness/rules/task_tracking.md.tmpl` | — |
| `harness/rules/version_control.md` | `harness/rules/version_control.md.tmpl` | — |
| `harness/rules/gpu.md` | `harness/rules/gpu.md.tmpl` | `ACCELERATORS_ENABLED=true` |
| `harness/templates/research_memo_template.md` | `harness/templates/research_memo_template.md.tmpl` | — |
| `harness/coding/tasks_working.md`, `tasks_finished.md`, `history.md` | `harness/coding/*.md.tmpl` | — (starter working-state files, blank; real content accrues per-project and is never re-rendered) |
| `harness/plans/next_steps.md`, `suggestions.md`, `goals.md`, `long_term.md`, `history.md` | `harness/plans/*.md.tmpl` | — (same starter/blank-skeleton pattern as `coding/` above) |
| `docs/RESULTS.md` | `docs/RESULTS.md.tmpl` | — |
| `docs/ARCHITECTURE.md` | `docs/ARCHITECTURE.md.tmpl` | — |
| `docs/references/needs_pdf.md` | `docs/references/needs_pdf.md.tmpl` | `LATEX_DRAFTING_ENABLED` toggles the theory/report clause in its "do not cite" wording |
| `docs/theory/README.md` | `docs/theory/README.md.tmpl` | `LATEX_DRAFTING_ENABLED=true` |
| `docs/report/README.md` | `docs/report/README.md.tmpl` | `LATEX_DRAFTING_ENABLED=true` |
| `harness/status.md` | `harness/status.md.tmpl` | — (starter, blank; real content accrues per-project and is never re-rendered) |
| `harness/status_history.md` | `harness/status_history.md.tmpl` | — (same starter/blank-skeleton pattern) |
| `harness/log.md` | `harness/log.md.tmpl` | — (same starter/blank-skeleton pattern, seeded with one entry recording the setup interview) |
| `AGENTS.md` | `AGENTS.md.tmpl` | — |
| `README.md` | `README.md.tmpl` | — |
| `.claude/settings.json` | `adapters/claude/settings.json.tmpl` | `ADAPTERS_ENABLED` includes `claude` |
| `.agents/hooks.json` | `adapters/antigravity/hooks.json.tmpl` | `ADAPTERS_ENABLED` includes `antigravity` |
| `docker-compose.yml` | `docker/docker-compose.yml.tmpl` | `DOCKER_ENABLED=true`; the `docker_gpu` section (an NVIDIA GPU device reservation) is further gated on `ACCELERATORS_ENABLED=true`. Each adapter's contribution is gated by `docker_agent_claude_compose` / `docker_agent_antigravity_compose`: its config volume (`claude-config`, `gemini-config`) and, for antigravity, the `ANTIGRAVITY_CONTAINER`/`CONTAINER_AUTO_ALLOW` environment variables that put `command_guard.py` in container mode. `agent-cache` is ungated (uv/pip/npm all use `~/.cache`), which also keeps the top-level `volumes:` map non-empty when no adapter is enabled. `name:` is pinned to `PROJECT_NAME_LOWER` so volume/container prefixes don't fall back to the directory basename. `.env` is mounted as an optional `env_file` (`required: false`) and `SSH_AUTH_SOCK` falls back to `/dev/null` when unset, so `docker compose config` succeeds on a fresh project with neither present |
| `Dockerfile` | `docker/Dockerfile.tmpl` | `DOCKER_ENABLED=true`; the image is otherwise driven entirely by existing config keys, no new interview questions. `PACKAGE_MANAGER` selects one package-manager install branch (`uv`, `poetry` via pipx, `pip` via apt python3-pip+venv, or `npm`/`pnpm`/`yarn` via NodeSource + corepack; anything else drops in a "none" branch with a comment on hand-adding conda/Miniforge). `ADAPTERS_ENABLED` selects agent CLI installs (`claude` → NodeSource Node + `npm install -g @anthropic-ai/claude-code`; `antigravity` → its official install script). Each adapter's block also pre-creates its own config directory (`/home/agent/.claude`, `/home/agent/.gemini`) owned by `agent`, so the matching named volume doesn't come up root-owned; `~/.cache` is created unconditionally. `LATEX_DRAFTING_ENABLED` gates the TeX Live install (several GB, off by default). See `docker_pm_*`/`docker_agent_*`/`docker_latex`/`docker_node_runtime` in `sections_to_drop()` |
| `docker/antigravity_settings.json` | `docker/antigravity_settings.json.tmpl` | `DOCKER_ENABLED=true` **and** `ADAPTERS_ENABLED` includes `antigravity`. Copied into the image at `~/.gemini/antigravity-cli/settings.json` (a path hardcoded in the `agy` binary). Carries the CLI's own permission policy — flat `permissions.allow`/`.ask`/`.deny` arrays of `command(...)`, `read_file(...)`, `write_file(...)`, `read_url(...)`, `mcp(...)` rules — which is a **separate layer** from `command_guard.py` and covers things the hook can't see (reading `~/.ssh/**`, writing `.git/**`, fetching a URL). Because a named volume is only initialized on first creation, changing this file needs `docker compose down -v`, not just a rebuild |
| `docker/entrypoint.sh` | `docker/entrypoint.sh.tmpl` | `DOCKER_ENABLED=true`; not internally gated by config — `AUTO_LAUNCH_AGENT=1` probes `PATH` at runtime for `claude` then `agy` (the Antigravity CLI's actual binary name — no `antigravity` binary is ever installed) and execs whichever is found, rather than being gated at render time on `ADAPTERS_ENABLED` (a render-time gate with no adapter enabled used to render an empty `if ...; then fi`, a bash syntax error that broke the entrypoint outright) |

### Real project data (never touched by friday)

`harness/plans/directives/<ID>.md` (all but `TEMPLATE.md`), and any raw
reference PDFs/`references.bib` under `docs/references/` are this project's
own live state — friday materializes the *starting* shape for the files
above once, then never touches them again (hand-edit freely); these other
files aren't in `MANIFEST.json` at all, not even as a one-time starter.

### `.gitignore` / `.gitattributes`

Not a manifest entry — `init_harness.py` appends
`setup/gitignore.fragment` and `setup/gitattributes.fragment` to the
project's own `.gitignore`/`.gitattributes` at sync time, one missing line
at a time, and never rewrites a file that already exists. Covers secrets
(`.env`, `harness.config.env`), gitignoring `harness/plans/directives/*.md`
while keeping `!TEMPLATE.md` tracked, and — when `LATEX_DRAFTING_ENABLED`
or the bibliography workflow are in use — LaTeX build artifacts, LFS-tracked
PDFs, and reference PDFs.
