# Changelog

## v0.8.0

Docker setup is now config-driven instead of one-size-fits-all, plus a
`USER_GUIDE.md` expansion landing in the same release.

**`Dockerfile` and `docker/entrypoint.sh` move from `symlinks` to
`materialize` in `MANIFEST.json`** — they're now rendered per-project
from `docker/Dockerfile.tmpl`/`docker/entrypoint.sh.tmpl`, not shared
byte-identical files. No new interview questions were added; the image
is driven entirely by existing `harness.config.env` keys:

- `PACKAGE_MANAGER` selects one package-manager install branch: `uv`,
  `poetry` (via pipx), `pip` (apt `python3-pip`+venv), or
  `npm`/`pnpm`/`yarn` (NodeSource + corepack). Anything else falls
  through to a "none" branch carrying a comment on where to hand-add
  conda/Miniforge.
- `ADAPTERS_ENABLED` selects agent CLI installs: `claude` pulls in
  NodeSource Node + `npm install -g @anthropic-ai/claude-code`;
  `antigravity` pulls in its official install script. Both, either, or
  neither.
- `LATEX_DRAFTING_ENABLED` now gates the TeX Live install, which used to
  default on via a host env var — several GB nobody outside the LaTeX
  suite wanted.
- `ACCELERATORS_ENABLED` gates the compose NVIDIA GPU device
  reservation.
- `docker-compose.yml`'s `.env` is now an optional `env_file`
  (`required: false`) and `SSH_AUTH_SOCK` tolerates being unset, so
  `docker compose config` succeeds on a fresh project with neither
  present.

Two real bugs were caught during verification and fixed:

- **Ubuntu 24.04 ships a default `ubuntu` user/group already at
  UID/GID 1000** — the default `USER_UID`/`USER_GID` here, and the UID/
  GID of most Linux desktop users. The old bare `groupadd -g 1000`
  build step collided with it and failed with exit 4. The Dockerfile
  now renames the incumbent user/group onto `agent` when the slot is
  taken, and only creates a fresh one when it's free.
- **The entrypoint's agent-CLI launch was render-time gated on
  `ADAPTERS_ENABLED`**, which produced an empty `if ...; then fi` — a
  bash syntax error that broke the container's entrypoint outright —
  whenever no adapter was enabled. It now probes `PATH` at runtime
  instead (`AUTO_LAUNCH_AGENT=1` tries `claude` then `antigravity`),
  which also means a CLI installed later is picked up without
  re-rendering.

- **Named volumes mounted root-owned.** `claude-config` and
  `claude-cache` mount at `/home/agent/.claude` and `/home/agent/.cache`,
  but neither path existed in the image — so Docker created both volumes
  owned by `root`, and the non-root `agent` user could never write them.
  `claude login` persistence, the documented reason the volume exists,
  had never actually worked. The image now pre-creates both directories
  owned by `agent` so the volume inherits that ownership on first mount.
  A project with pre-existing root-owned volumes needs one
  `docker compose down -v` to discard them.

**Existing Docker-enabled projects**: because `Dockerfile` and
`docker/entrypoint.sh` move from symlinked to materialized, pulling
this release alone does not update them in a project that already has
Docker enabled — `init_harness.py` never overwrites a materialized file
that already exists. Run `--force-materialize=Dockerfile
--force-materialize=docker/entrypoint.sh` (or reconfigure) to pick up
the new, parameterized versions, then `docker compose build` again.

`README.md`, `README.md.tmpl`, and `AGENTS.md.tmpl` updated to describe
the new materialized Docker files and their gating; `harness/
USER_GUIDE.md` gained a corresponding operator-facing expansion in this
same release, covering day-to-day use of the now-configurable image.

## v0.7.0

Alignment pass closing the gap between a freshly generated friday harness
and heimdall's own, live one.

**The three missing harness state files now exist.** `harness/status.md`,
`harness/status_history.md`, and `harness/log.md` were referenced 52 times
across `harness.md.tmpl`, all seven role contracts, five rules docs,
`README.md.tmpl`, `AGENTS.md.tmpl`, `check_md_hygiene.py`'s `FILE_CAPS`, and
`init_harness.py`'s own closing checklist — but were absent from
`MANIFEST.json` entirely, so a fresh project's central rule-3 invariant
pointed at a file that did not exist. All three are now `materialize`
entries seeded from heimdall's live files, with project bodies emptied to
`_(none)_`/`(none yet)` and tracker/accelerator wording gated the same way
as everywhere else.

**Fixed `check_md_hygiene.py` silently no-op'ing in every consumer
project.** Its `REPO_ROOT` was computed as
`Path(__file__).resolve().parents[2]`; reached through the `.claude/hooks/`
symlink, `.resolve()` followed the link into `.friday/adapters/hooks/`,
landing `REPO_ROOT` on `.friday/` itself instead of the consumer repo. Every
capped path then missed `path.exists()` and was silently skipped — the
pre-commit hook and the Planner/Reviewer pass-start hygiene check both
looked healthy while checking nothing. Confirmed live in heimdall before
the fix. Replaced with an upward search for the consumer repo root (a
directory containing `harness.config.env`, or failing that `.gitmodules` +
`.friday/`), matching the convention `harness/tools/_config.py` already
documents. **This is a behavioral change for every existing consumer
project**: the checker was silently passing before and will now actually
report files over their line cap. Added
`adapters/hooks/test_check_md_hygiene.py` as a regression guard for the
exact symlink-resolution failure that shipped silently.

**`command_guard.py` is no longer hardcoded to `uv`/`latexmk`.** Its
allow-list and force-ask patterns now derive from `harness.config.env`
(`PACKAGE_MANAGER_SYNC_CMD`, `PACKAGE_MANAGER_RUN_CMD`, `TEST_CMD`,
`PACKAGE_MANAGER_ADD_CMD`, and LaTeX patterns only when
`LATEX_DRAFTING_ENABLED=true`) instead of literal `uv`/`latexmk` strings, so
a poetry/npm project gets a real allow-list instead of everything degrading
to `force_ask`. Falls back to today's `uv`+LaTeX literals if
`harness.config.env` is missing or unparseable, so behavior never regresses
before setup writes a config.

Two follow-on defects in that derivation were caught in review and fixed:

- The upward search stopped at the first directory containing a `.git`
  entry. In a submodule `.friday/.git` is a *file*, so any invocation whose
  cwd sat inside `.friday/` hit that boundary, found no config, and fell
  through to the `uv`+LaTeX fallback — auto-allowing `uv sync` and `latexmk`
  on a project that uses neither, while pushing that project's own commands
  to `force_ask`. A guardrail silently enforcing a *different* project's
  policy is worse than one that is merely absent. The boundary break is
  gone, and the search now tries cwd first and then the *unresolved*
  `Path(__file__).parent` (the symlink's own directory), matching
  `check_md_hygiene.py`'s `find_repo_root()`. Regression test added.
- Deriving purely from config was narrower than the hardcoded list it
  replaced: `uv lock` and a bare `pytest` (the old pattern matched
  `^(uv\s+run\s+)?pytest`) both silently lost their auto-allow. Safe
  lockfile/refresh verbs are now derived per package manager, and when
  `TEST_CMD` is `RUN_CMD` plus a runner, the bare runner is allowed too.
  This gap was invisible to the original test suite because the `.git`
  boundary above meant those tests never found a config and only ever
  exercised the fallback path.

**`init_harness.py`/`MANIFEST.json`**: `docker_quickstart` and
`lfs_policy` SECTION axes are now gated (`DOCKER_ENABLED`,
`LATEX_DRAFTING_ENABLED`) instead of shipping into every project
regardless of whether Docker or the LaTeX suite are in use;
`harness/running/logs/` is now created at sync (the directory
`environment.md.tmpl` already documents launches redirecting into);
`closing_checklist()`'s marker scan now covers `docs/**/*.md`, not just
`harness/**/*.md` + `AGENTS.md` + `README.md`; ships
`setup/gitignore.fragment` and `setup/gitattributes.fragment`, applied by
appending missing lines idempotently — never rewriting a consumer's
existing file — covering secrets, gitignoring
`harness/plans/directives/*.md` (with `!TEMPLATE.md` kept tracked), and
LaTeX/reference artifacts when those axes are enabled.

**Template prose**: `README.md.tmpl` gained the LaTeX build section
(`latexmk` commands under `docs/{theory,report}/<content-slug>/`) that
every other doc already gated on the LaTeX axis but this one had lost;
`environment.md.tmpl` no longer leaves a blank gap when the non-matching
launch-method section is dropped, and keeps a two-line cross-reference to
the other launch patterns so a systemd project doesn't lose the
`setsid`/`nohup` fallback knowledge entirely; `AGENTS.md.tmpl`'s
command-guard bullets now render the real `PACKAGE_MANAGER_*` tokens
instead of `[SET AT SETUP: ...]` placeholders, matching what B2's
config-driven `command_guard.py` actually does; `docs/ARCHITECTURE.md.tmpl`'s
source-dir marker is now a single clean `[SET AT SETUP: ...]` the closing
checklist's `docs/**/*.md` scan will surface; removed heimdall-specific
text (`JAX`, "David") from `USER_GUIDE.md` and the bibliography tool
docstrings, which are symlinked unmodified into every project.

**`setup/SETUP.md`**: fixed heading numbering after the "Detached
background jobs" topic moved later in the interview order; replaced the
`.gitignore`-correctness hand-wave with a description of the new
fragment-based mechanical behavior; the closing description of what setup
produces now accounts for the three new state files, `harness/running/
logs/`, and the `.gitignore`/`.gitattributes` step.

**Also caught in review**: the `docker_quickstart` block in
`README.md.tmpl` carried a comment claiming `init_harness.py` fills in the
compose commands, which it never did — gating it on `DOCKER_ENABLED` fixed
the non-Docker case but left the false claim shipping to every *Docker*
project, so the block now holds the real `docker compose`
build/up/exec/down commands. Two more blank-gap bugs of the same shape as
`environment.md.tmpl`'s were fixed in `task_tracking.md.tmpl` (between the
gated tracker sections) and `author.md.tmpl` (between the gated LaTeX
sections). Remaining heimdall-specific text was genericized in
`harness/roles/researcher.md.tmpl` ("David" → "the operator", three
places) and `version_control.md.tmpl`'s commit-message examples, both of
which are shared across every consumer project.

## v0.6.0

Consumer projects now get a templated `docs/` and `harness/{coding,plans}/`
scaffold instead of inventing that shape from scratch on first use — the
same "make it a real template axis, not implicit convention" move already
applied to the LaTeX suite (v0.5.0) and GPU support (v0.3.0).

New materialized starters (each rendered once at setup, never re-synced —
hand-edit freely afterward): `docs/RESULTS.md`, `docs/ARCHITECTURE.md`,
`docs/references/needs_pdf.md` (its "do not cite" wording is `latex_on`/
`latex_off`-gated, same mechanism as the role files), and blank-skeleton
`harness/coding/{tasks_working,tasks_finished,history}.md` +
`harness/plans/{next_steps,suggestions,goals,long_term,history}.md`. New
symlinked (pure generic, zero project content) namespace READMEs:
`harness/{research,review,running}/README.md` and `docs/references/
inbox/README.md`. New `LATEX_DRAFTING_ENABLED`-gated materialized files:
`docs/theory/README.md` and `docs/report/README.md`, documenting the
self-contained-latexmk-project convention on disk instead of only in role
prose. `materialize_files()` gained a `"latex"` manifest-entry gate
(mirrors the existing `"accelerators"`/`"docker"` gates); `AGENTS.md.tmpl`
gained a `latex_on`-gated "LaTeX/Beamer drafting suite" project-facts row;
`closing_checklist()`'s LaTeX reminder is now a real presence check instead
of an unconditional TODO line.

`docs/AGENTS.md.tmpl` and `docs/README.md.tmpl` move to this repo's root
(`AGENTS.md.tmpl`, `README.md.tmpl`) — `docs/` was only ever holding those
two unrelated files, and freeing it up lets it literally mirror a consumer
project's real `docs/` tree instead of colliding with it.

## v0.5.0

Makes the LaTeX/Beamer drafting suite (`docs/theory/` for the Researcher,
`docs/report/` for the Author, self-contained `latexmk` projects citing the
shared `docs/references/references.bib`) an optional, config-gated axis
instead of content hardcoded into files that were supposed to be
byte-identical across every project — the same bug class already fixed
once for GPU support. New `LATEX_DRAFTING_ENABLED` key (SETUP.md §9,
alongside the bibliography-tooling questions, which stay unconditional —
the references/inbox/`.bib` workflow was already generic and needed no
change).

`harness/roles/researcher.md`, `author.md`, and `reviewer.md` move from
plain `symlinks` entries to `materialize`/`.tmpl` entries in
`MANIFEST.json`, each gaining `<!-- SECTION:latex_on/latex_off:start/end
-->` variants (mirrors `harness.md`'s `accel_none`/`accel_present` split).
With the suite off, Researcher and Author keep every other duty (memos,
citations, `docs/RESULTS.md`) — their "formal writeup" output is just a
Markdown doc instead of a separate LaTeX project. `init_harness.py` gained
`LATEX_SECTIONS` + a `sections_to_drop()` branch, an interview question,
and a closing-checklist reminder (LFS/`docs/theory,report` setup) when
enabled. The Claude/Antigravity adapter `description:` frontmatter for
these two roles was reworded to be true either way, rather than templated
— those files stay symlink-source.

## v0.4.1

Documentation only. Replaced README's terse "see MANIFEST.json" pointer
with an actual inline breakdown of every symlinked and materialized path,
grouped by directory, generated from and cross-checked against
`MANIFEST.json` — plus a "real project data" section listing what friday
never touches. Points back to `sync_symlinks()`/`materialize_files()` in
`setup/init_harness.py` as the code that implements it.

## v0.4.0

`USER_GUIDE.md` is now a generic, non-templated file living at this repo's
root — symlinked into every consumer project as `harness/USER_GUIDE.md`
instead of being materialized from a per-project `.tmpl`. It's readable
natively on GitHub, updates automatically the moment a project's `.friday/`
checkout advances (no re-materialize step), and never drifts per project.
Project-specific operational content that used to live in it (results doc
path, tracker specifics, project layout) moved to `AGENTS.md`, which already
carries per-project facts — added a `Docker dev container` row there too.
Expanded the guide's Docker section into a full lifecycle walkthrough:
installing Docker, building the image, entering the container, day-to-day
workflow, and adding volumes later. Removed `init_harness.py`'s
`write_user_guide_docker_section()` (the per-project auto-refreshed Docker
blurb it maintained no longer applies to a shared, symlinked file).

`README.md` expanded with a full getting-started walkthrough and a new
"Updating the harness" section documenting both the plain git-submodule
update sequence and the `harness_sync.sh` convenience wrapper, including
the exact one-liner to add the project-owned `harness.sh` entry point that
was previously only mentioned, never actually explained.

Fixed a false positive in `closing_checklist()`: it was scanning symlinked
(shared, generic) `.md` files for leftover `[SET AT SETUP: ...]` markers,
which would flag `USER_GUIDE.md` forever since its Docker section
legitimately mentions that placeholder syntax in prose. Symlinked files are
now skipped — only materialized per-project files can have a genuine
unfilled placeholder.

## v0.3.0

Restores functionality dropped during the original `SETUP.md` migration
(caught by diffing against the pre-migration interview):

- GPU/accelerator support as a real template axis again: `harness/rules/gpu.md.tmpl`
  (device table + allocation policy), `harness/harness.md` now templated
  (`harness.md.tmpl`) with `accel_none`/`accel_present` section variants for
  rules 10/14, and `environment.md.tmpl`'s accelerator note now
  auto-drops/keeps with the same `ACCELERATORS_ENABLED` key. New SETUP.md §4.
- `check_agent_spawn.py`'s `HIGH_TIER_KEYWORDS` now reads
  `HIGH_TIER_MODEL_KEYWORDS` from `harness.config.env` at hook run time
  instead of a hardcoded tuple the interview's answer never reached.
- SETUP.md §2 (repository layout) restored — writes into `AGENTS.md`
  §Repository Layout and reviews `.gitignore`.
- `closing_checklist()` restored to parity with the original: fixed a bug
  where the leftover-marker scan only matched ALL-CAPS token placeholders
  and silently missed free-text `[SET AT SETUP: ...]` prose markers; added
  reminders for the md-hygiene hook, `status.md` accuracy, opening a first
  directive, and recording surprises in `harness/log.md`.

## v0.2.0

Restores `setup/SETUP.md` as the full agent-led conversational interview
(judgment, adaptive questioning, real setup actions) that writes
`harness.config.env` and hands off to `init_harness.py` for the mechanical
work — this was referenced in docs from v0.1.0 but never actually written.

## v0.1.1

Fixes a `REPO_ROOT` symlink-resolution bug: `Path(__file__).resolve()`-based
root-finding in the bibliography tools followed symlinks into `.friday/`
instead of resolving to the consumer project. Replaced with an
upward-search-from-`cwd()` `find_repo_root()` in `harness/tools/_config.py`.

## v0.1.0

Initial extraction from the Heimdall project's harness. Portable core
(`harness.md`, role contracts, generic rules, both adapters' hooks/agent
definitions), templated project-specific docs (`environment.md`,
`task_tracking.md`, `version_control.md`, `USER_GUIDE.md`, `AGENTS.md`,
`README.md`, bibliography-tool template), config-driven bibliography
tooling, consolidated hook implementations (fixes the `.claude/` vs.
`.agents/` hook drift), `init_harness.py` setup/sync script, and a Docker
dev-container setup (Ubuntu base, Claude Code CLI inside the container).
