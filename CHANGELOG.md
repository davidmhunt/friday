# Changelog

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
