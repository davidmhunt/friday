# friday

A portable multi-agent development harness — a lead-and-delegate team
(a Controller that is your single point of contact; Planner, Architect,
Coder, Runner, Researcher, Author, Editor and Reviewer as its specialists;
plus any project-specific specialists you add), a shared loop and rule set,
adapters for Claude Code and Antigravity, hook-based guardrails, and a
Docker dev-container setup. Drop it into a project as a git
submodule, run the setup interview once, and get a working harness without
re-authoring it.

The full operator manual — how the lead-mode loop works (goal →
Controller → Planner proposes directives → you approve → specialists
execute → Reviewer closes), where status lives, how to feed the agents
inputs — is `USER_GUIDE.md` in this repo, a short operator guide. It's the same
file for every project (symlinked in as `.friday/active/harness/USER_GUIDE.md`,
never templated), so read it here or in any consumer project. Deep reference
(hooks, rules index, state files, updating, Docker, troubleshooting) lives in
`reference/`, read in place at `.friday/reference/` and not symlinked.

**Doc split**: this `README.md` covers installing, updating, and porting
friday itself (installer + maintainer concerns). `.friday/active/harness/USER_GUIDE.md`
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
3. **What that leaves you with**: a symlink tree (`.friday/active/harness/`,
   `.claude/`, `.agents/`) pointing into `.friday/` for everything identical
   across every project, plus real materialized copies of anything needing
   project-specific customization (`harness.md`, the project-facing rules
   docs, the Researcher/Author/Reviewer role contracts, `AGENTS.md`,
   `README.md`, `harness.sh`, and — if Docker/accelerators are enabled —
   the `docker/` files and `gpu.md`), a starter `docs/` scaffold
   (`RESULTS.md`, `ARCHITECTURE.md`, `references/` with its inbox +
   `needs_pdf.md`, and `theory/`/`report/` if the LaTeX suite is on), and
   the harness state files, seeded empty and ready to use:
   `.friday/active/harness/status.md`, `log.md`, `status_history.md` (at
   `docs/status_history.md` instead when no tracker is configured),
   `plans/goals.md`, `plans/history.md`, the directive `TEMPLATE.md` and
   `running/logs/`. `init_harness.py` also appends the `.gitignore` /
   `.gitattributes` fragments (secrets, Python/uv cruft, and
   LaTeX/reference artifacts when those axes are enabled), one missing line
   at a time, and lists the harness-owned files in the local
   `.git/info/exclude`. `AGENTS.md` is the one file every agent session
   loads first — it's where this project's own facts (name, working root,
   results doc, package manager, task tracker, repository layout) live.
4. **Start working**: `claude --agent controller` (or tell a session "you
   are the controller") and give it a goal. It asks what it needs, has the
   Planner propose directives, and runs nothing until you approve each
   one. See `USER_GUIDE.md` ("The workflow") for the full workflow.
5. **Optional — project-specific specialists.** If the project has a domain
   the core roles shouldn't own (board design, a firmware toolchain), add a
   role in the project's own repo: `.friday-project/roles/<role>.md` plus
   its adapter files. See "Project-owned extensions" below and
   `templates/examples/project_roles/`.

A human can also skip the agent and either hand-write `harness.config.env`
(see `setup/harness.config.env.example`) or run the script's own bare
interactive interview directly:

```bash
python3 .friday/setup/init_harness.py              # interview if no config yet, else re-sync
python3 .friday/setup/init_harness.py --reconfigure  # re-run the interview
```

Either way, re-running is idempotent and won't overwrite files you've
hand-edited — it prints a `SKIP` line and tells you to pass
`--force-materialize=<path>` if you want a fresh render instead. Use
`--dry-run` first to see what a run would do.

Before the first real session, fill in any `[SET AT SETUP: ...]` markers the
closing checklist lists (project overview, repository layout), create a
working branch (roles commit on any non-`main` branch), and write the
project's objectives in `.friday/active/harness/plans/goals.md`.

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
docs, `AGENTS.md`, `README.md`, the `docker/` files) don't auto-update —
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

**Upgrading across a release that changes file shapes** (e.g. v0.17 →
v0.18 "lead mode"): the `CHANGELOG.md` entry for that release ends with a
"Migrating an existing project" checklist (which files to force-render,
which to restructure by hand, which retired files to archive), and
`reference/updating.md` summarizes it. Run `init_harness.py --dry-run` first
and read the `REFUSE`, `SKIP` and `RETIRED` lines.

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
`init_harness.py` generates and makes it executable for you as part of the
normal setup/sync run described above — there's no separate step to add it
by hand.

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

`MANIFEST.json` (`MANIFEST_VERSION: 2`) is the single source of truth for
this — every path below is a literal `dest` entry there, and
`sync_symlinks()` / `materialize_files()` in `setup/init_harness.py` are
what actually create them. This section is a human-readable rendering of
that manifest, grouped by directory; if the two ever disagree,
`MANIFEST.json` is authoritative.

### Symlinked (shared — edit in `.friday/`, every project sees it next pull)

These files are byte-identical across every project by design. Their
symlinks all point back into this repo's checkout at `.friday/`; nothing
about them is ever rendered or project-specific.

| Consumer path | Points into `.friday/` | Notes |
|---|---|---|
| `.friday/active/harness/USER_GUIDE.md` | `USER_GUIDE.md` | the short operator guide (deep reference is read in place at `.friday/reference/`) |
| `.friday/active/harness/roles/{architect,coder,controller,editor,planner,runner}.md` | `templates/harness/roles/` | 6 of the 9 core role contracts, always present — an unused role is inert (only read when a session is assigned that role), so there's no pruning step |
| `.friday/active/harness/rules/{conventions,md_hygiene,monitoring,checkpoint_compat,data_artifacts,document_budgets}.md` | `templates/harness/rules/` | the 6 rules docs with zero project-specific content |
| `.friday/active/harness/plans/directives/TEMPLATE.md` | `templates/harness/plans/directives/` | the directive template every real directive is copied from (goal, Steps, `Verify:`, out of scope, open questions, Log, Amendments) |
| `.friday/active/harness/templates/spec_template.md` | `templates/harness/templates/` | the Architect's ≤ 2-page requirements-spec template |
| `.friday/active/harness/review/README.md`, `.friday/active/harness/running/README.md` | same paths, under `templates/harness/` | namespace explainers for the Reviewer/Runner working directories — zero project-specific content |
| `docs/research/README.md` | `templates/docs/research/` | namespace explainer for the Researcher's memo directory — lives at the project root (tracked, not gitignored) since research memos must survive the harness being removed, unlike the `active/`-rooted rows above |
| `docs/references/inbox/README.md` | `templates/docs/references/inbox/` | explains the drop-a-PDF-here + `intake_references.py` workflow |
| `.friday/active/harness/tools/{_config,intake_references,verify_references,check_unavailable_sources,lint_research_memo,find_open_access_pdf}.py` | `templates/harness/tools/` | bibliography-workflow tools; config-driven via `harness.config.env` (see `.friday/active/harness/tools/_config.py`), not templated. `intake_references`, `check_unavailable_sources` and `find_open_access_pdf` (and `docs/references/inbox/README.md`) are linked only when `BIBLIO_CONTACT_EMAIL` or `BIBLIO_USER_AGENT_TOKEN` is non-empty (there is no separate on/off key; the same gate controls `docs/references/needs_pdf.md` and the reference-PDF `.gitignore` lines) |
| `.claude/agents/{architect,author,coder,controller,editor,planner,researcher,reviewer,runner}.md` | `templates/adapters/claude/agents/` | Claude Code role adapter files — present only if `ADAPTERS_ENABLED` includes `claude` |
| `.claude/hooks/{check_agent_spawn,check_md_hygiene,check_commit_msg,command_guard}.py`, `.claude/hooks/{pre-commit,commit-msg,README.md}` | `templates/adapters/hooks/` | same physical files as `.agents/hooks/*` below — one canonical implementation, two symlink targets (each adapter's copy is present only if that adapter is in `ADAPTERS_ENABLED`; the hooks' unit tests stay in `templates/adapters/hooks/test_*.py` and are not linked) |
| `.agents/hooks/{check_agent_spawn,check_md_hygiene,check_commit_msg,command_guard}.py`, `.agents/hooks/{pre-commit,commit-msg,README.md}` | `templates/adapters/hooks/` | same canonical files as the `.claude/hooks/*` row above |
| `.git/hooks/{pre-commit,commit-msg}` | *(anchored to `.claude/hooks/`, per `MANIFEST.json`'s `git_hooks` key — not a manifest `symlinks` entry)* | a second-order symlink: `.git/hooks/*` → `.claude/hooks/*` → `.friday/templates/adapters/hooks/*`; installed by `install_git_hooks()` |

### Materialized (real per-project copies, rendered once)

These start life as a `.tmpl` file in `.friday/`, get their `[SET AT
SETUP: ...]` tokens substituted and inapplicable `<!-- SECTION -->` blocks
dropped by `render()`, and are written as ordinary files in the consumer
project — safe to hand-edit afterward. `init_harness.py` never overwrites
one that already exists and differs from a fresh render; use
`--force-materialize=<path>` to force a re-render.

| Consumer path | Template source in `.friday/` | Gated by |
|---|---|---|
| `.friday/active/harness/harness.md` | `templates/harness/harness.md.tmpl` | — |
| `.friday/active/harness/roles/researcher.md` | `templates/harness/roles/researcher.md.tmpl` | `LATEX_DRAFTING_ENABLED` toggles the `docs/theory/` namespace text |
| `.friday/active/harness/roles/author.md` | `templates/harness/roles/author.md.tmpl` | `LATEX_DRAFTING_ENABLED` toggles the `docs/report/` namespace + Slide decks section |
| `.friday/active/harness/roles/reviewer.md` | `templates/harness/roles/reviewer.md.tmpl` | `LATEX_DRAFTING_ENABLED` toggles the theory/report clause in the citation-check step |
| `.friday/active/harness/rules/environment.md` | `templates/harness/rules/environment.md.tmpl` | — |
| `.friday/active/harness/rules/task_tracking.md` | `templates/harness/rules/task_tracking.md.tmpl` | — |
| `.friday/active/harness/rules/version_control.md` | `templates/harness/rules/version_control.md.tmpl` | — |
| `.friday/active/harness/rules/gpu.md` | `templates/harness/rules/gpu.md.tmpl` | `ACCELERATORS_ENABLED=true` |
| `.friday/active/harness/templates/research_memo_template.md` | `templates/harness/templates/research_memo_template.md.tmpl` | — |
| `.friday/active/harness/plans/goals.md`, `history.md` | `templates/harness/plans/*.md.tmpl` | — (starter skeletons; real content accrues per-project and is never re-rendered). `coding/` and `plans/{next_steps,suggestions,long_term}.md` were retired in v0.18.0 — see MANIFEST.json `retired_dests` |
| `docs/RESULTS.md` | `templates/docs/RESULTS.md.tmpl` | — |
| `docs/ARCHITECTURE.md` | `templates/docs/ARCHITECTURE.md.tmpl` | — |
| `docs/references/needs_pdf.md` | `templates/docs/references/needs_pdf.md.tmpl` | `LATEX_DRAFTING_ENABLED` toggles the theory/report clause in its "do not cite" wording |
| `docs/theory/README.md` | `templates/docs/theory/README.md.tmpl` | `LATEX_DRAFTING_ENABLED=true` |
| `docs/report/README.md` | `templates/docs/report/README.md.tmpl` | `LATEX_DRAFTING_ENABLED=true` |
| `.friday/active/harness/status.md` | `templates/harness/status.md.tmpl` | — (starter, blank; real content accrues per-project and is never re-rendered) |
| `.friday/active/harness/status_history.md` **or** `docs/status_history.md` | `templates/harness/status_history.md.tmpl` | with a tracker configured it lives in the gitignored `.friday/active/harness/`; with `TRACKER_KIND=none` it is materialized into the project repo (`docs/`, tracked) so the record of closed work survives a fresh clone. Same blank-skeleton pattern |
| `.friday/active/harness/log.md` | `templates/harness/log.md.tmpl` | — (same starter/blank-skeleton pattern, seeded with one entry recording the setup interview) |
| `AGENTS.md` | `templates/AGENTS.md.tmpl` | — |
| `README.md` | `templates/README.md.tmpl` | — (seeded once: a later difference from a fresh render is expected and never reported) |
| `harness.sh` | `templates/harness.sh.tmpl` | — (seeded once; the thin wrapper around `.friday/setup/harness_sync.sh`) |
| `.claude/settings.json` | `templates/adapters/claude/settings.json.tmpl` | `ADAPTERS_ENABLED` includes `claude` |
| `.agents/hooks.json` | `templates/adapters/antigravity/hooks.json.tmpl` | `ADAPTERS_ENABLED` includes `antigravity` |
| `.agents/agents/{architect,architect-heavy,author,coder,coder-heavy,controller,editor,editor-heavy,planner,planner-heavy,researcher,researcher-heavy,researcher-quick,reviewer,reviewer-heavy,runner,runner-judgment}.md` | `templates/adapters/antigravity/agents/` | `ADAPTERS_ENABLED` includes `antigravity` (role + tier-variant adapter files) |
| `.dockerignore` | `templates/docker/.dockerignore.tmpl` | `DOCKER_ENABLED=true`; the only Docker file that lives at the repo root rather than in `docker/`, because Compose reads `.dockerignore` from the build-context root |
| `docker/docker-compose.harness.yml` | `templates/docker/docker-compose.harness.yml.tmpl` | `DOCKER_ENABLED=true`; a harness-only Compose *override* (never committed by a project; re-rendered on every sync): `target: harness`, plus each adapter's config volume (`claude-config`, `gemini-config`) and, for antigravity, the `ANTIGRAVITY_CONTAINER`/`CONTAINER_AUTO_ALLOW` environment variables that put `command_guard.py` in container mode (gated by `docker_agent_claude_compose` / `docker_agent_antigravity_compose`). `init_harness.py` also writes `COMPOSE_FILE=docker/docker-compose.yml:docker/docker-compose.harness.yml` into the root `.env` so plain `docker compose` stacks both |
| `docker/docker-compose.yml` | `templates/docker/docker-compose.yml.tmpl` | `DOCKER_ENABLED=true`; the project-owned base file (`target: dev`, no agent tooling). The `docker_gpu` section (an NVIDIA GPU device reservation) is further gated on `ACCELERATORS_ENABLED=true`. `agent-cache` is ungated (uv/pip/npm all use `~/.cache`), which also keeps the top-level `volumes:` map non-empty. `name:` is pinned to `PROJECT_NAME_LOWER` so volume/container prefixes don't fall back to the directory basename. `.env` is mounted as an optional `env_file` (`required: false`) and `SSH_AUTH_SOCK` falls back to `/dev/null` when unset, so `docker compose config` succeeds on a fresh project with neither present |
| `docker/Dockerfile` | `templates/docker/Dockerfile.tmpl` | `DOCKER_ENABLED=true`; the image is otherwise driven entirely by existing config keys, no new interview questions. `PACKAGE_MANAGER` selects one package-manager install branch (`uv`, `poetry` via pipx, `pip` via apt python3-pip+venv, or `npm`/`pnpm`/`yarn` via NodeSource + corepack; anything else drops in a "none" branch with a comment on hand-adding conda/Miniforge). `ADAPTERS_ENABLED` selects agent CLI installs, in the `harness` stage only (`claude` → NodeSource Node + `npm install -g @anthropic-ai/claude-code`; `antigravity` → its official install script). Each adapter's block also pre-creates its own config directory (`/home/agent/.claude`, `/home/agent/.gemini`) owned by `agent`, so the matching named volume doesn't come up root-owned; `~/.cache` is created unconditionally. `LATEX_DRAFTING_ENABLED` gates the TeX Live install (several GB, off by default). See `docker_pm_*`/`docker_agent_*`/`docker_latex`/`docker_node_runtime` in `sections_to_drop()` |
| `docker/antigravity_settings.json` | `templates/docker/antigravity_settings.json.tmpl` | `DOCKER_ENABLED=true` **and** `ADAPTERS_ENABLED` includes `antigravity`. Copied into the image at `~/.gemini/antigravity-cli/settings.json` (a path hardcoded in the `agy` binary). Carries the CLI's own permission policy — flat `permissions.allow`/`.ask`/`.deny` arrays of `command(...)`, `read_file(...)`, `write_file(...)`, `read_url(...)`, `mcp(...)` rules — which is a **separate layer** from `command_guard.py` and covers things the hook can't see (reading `~/.ssh/**`, writing `.git/**`, fetching a URL). Because a named volume is only initialized on first creation, a rebuild alone won't push a changed copy into an existing `gemini-config` volume — but `entrypoint.sh` re-syncs this one file from the bind-mounted repo on every container start, so a plain restart (`docker compose -f docker/docker-compose.yml up -d`) is enough to pick up the change; `down -v` is not needed |
| `docker/entrypoint.sh` | `templates/docker/entrypoint.sh.tmpl` | `DOCKER_ENABLED=true`; not internally gated by config — `AUTO_LAUNCH_AGENT=1` probes `PATH` at runtime for `claude` then `agy` (the Antigravity CLI's actual binary name — no `antigravity` binary is ever installed) and execs whichever is found, rather than being gated at render time on `ADAPTERS_ENABLED` (a render-time gate with no adapter enabled used to render an empty `if ...; then fi`, a bash syntax error that broke the entrypoint outright) |

Not a `MANIFEST.json` entry: `docker/.env`, a relative symlink to `../.env`
that `init_harness.py` creates (and re-creates on every sync) whenever
`DOCKER_ENABLED=true`. Compose resolves a bare `.env` against the compose
file's own directory (`docker/`, now that all Docker inputs live there),
not the repo root, so without this symlink a root-only `.env` is silently
ignored and `${USER_UID}` falls back to `1000` — breaking bind-mount file
ownership for any host user whose UID isn't 1000. The symlink is allowed to
dangle: Compose treats a missing `.env` as "no overrides," so a project
that has never created one still works.

### Project-owned extensions (`.friday-project/`, never touched by friday)

A project adds its own specialist roles here, tracked in the project's own
repo. Each `.friday-project/roles/<role>.md` is linked by
`init_harness.py` into `.friday/active/harness/roles/<role>.md` (a
consumer → consumer symlink, re-created on every sync, stale links removed),
and discovered at run time by `check_agent_spawn.py` (spawn-title check,
`<role>-heavy` escalation variant) and `check_commit_msg.py` (`<Role>:`
prefix, directive/tracker body). The role's adapters —
`.claude/agents/<role>.md`, `.agents/agents/<role>{,-heavy}.md` — are
ordinary project files: not in `MANIFEST.json`, never rendered, overwritten
or added to `.git/info/exclude`. `init_harness.py` warns if an enabled
adapter is missing or git-ignored. A core role name can't be reused. Worked
example: `templates/examples/project_roles/hardware/`.

### Real project data (never touched by friday)

`.friday/active/harness/plans/directives/<ID>.md` (all but `TEMPLATE.md`), and any raw
reference PDFs/`references.bib` under `docs/references/` are this project's
own live state — friday materializes the *starting* shape for the files
above once, then never touches them again (hand-edit freely); these other
files aren't in `MANIFEST.json` at all, not even as a one-time starter.

### `.gitignore` / `.gitattributes`

Not a manifest entry — `init_harness.py` appends
`setup/gitignore.fragment` and `setup/gitattributes.fragment` to the
project's own `.gitignore`/`.gitattributes` at sync time, one missing line
at a time, and never rewrites a file that already exists. Covers secrets
(`.env`, `harness.config.env`), Python/uv cruft, reference PDFs and the
inbox when the bibliography workflow is in use, and — when
`LATEX_DRAFTING_ENABLED` — LaTeX build artifacts and LFS tracking of
generated `docs/theory/`/`docs/report/` PDFs. Harness state under
`.friday/active/` needs no entry: it is gitignored inside the submodule, and
harness-owned files in the project are listed in the local
`.git/info/exclude`.
