# Changelog

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
