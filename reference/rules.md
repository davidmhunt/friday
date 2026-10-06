# The rules system

Index of the numbered harness rules, the detail doc behind each, and which rules vary per project. Back to the [User Guide](../USER_GUIDE.md).

Every role follows the same numbered rules — they live in
`.friday/active/harness/harness.md` (rendered from `templates/harness/harness.md.tmpl`), which
stays deliberately lean: each rule is stated as an invariant plus a
**trigger** naming a detail doc under `.friday/active/harness/rules/*.md`. Roles read
`.friday/active/harness/harness.md` every pass, but only read a rule's detail doc when
their next action actually matches that rule's trigger — that's the
token-budget contract that keeps every session from re-reading the whole
rule set in full on every pass.

An index, so you know what governs a given situation without having to
open `harness.md` yourself:

| # | Covers | Detail doc |
|---|--------|------------|
| 1 | Shared-artifact namespacing — never mutate a data artifact an existing run consumes | `.friday/active/harness/rules/data_artifacts.md` |
| 2 | Single source of truth for result numbers (this project's results doc) | — |
| 3 | `status.md` ownership — loops, directive rows, and close-out into `status_history.md` + `closed/` | — |
| 4 | Checkpoint/model compatibility for forward-pass-altering changes | `.friday/active/harness/rules/checkpoint_compat.md` |
| 5 | Eval provenance sidecars + a completion self-check before reporting any eval done | `.friday/active/harness/rules/data_artifacts.md` |
| 6 | Pre-mutation snapshots of canonical data | `.friday/active/harness/rules/data_artifacts.md` |
| 7 | Monitor heartbeat — a stale timestamp means "monitor dead, verify directly" | `.friday/active/harness/rules/monitoring.md` |
| 8 | Markdown hygiene — line caps on `status.md`, `goals.md`, open directives | `.friday/active/harness/rules/md_hygiene.md` |
| 9 | Controlled reproduction required before recording a root-cause claim as fact | — |
| 10 | Accelerator allocation | **Config-dependent** — see below |
| 11 | Fail-loud numerical guards — a skipped-batch guard must also catch permanent collapse | `.friday/active/harness/rules/monitoring.md` |
| 12 | Recording finished work — each role commits its own scoped paths, attributed | `.friday/active/harness/rules/version_control.md` |
| 13 | External tracker sync (opt-in) — issue opened at approval, closed at close-out | `.friday/active/harness/rules/task_tracking.md` |
| 14 | *(project-specific — see below)* | — |
| 15 | Detached background launches — never a bare `cmd &` in an interactive shell | `.friday/active/harness/rules/environment.md` |
| 16 | Document budgets & concision for `[doc]` directives and specs | `.friday/active/harness/rules/document_budgets.md` |
| 17 | Context hygiene — grep then read ranges, filter build/test output, one worker per Step | `.friday/active/harness/rules/context_hygiene.md` |
| 18 | Long runs (> ~4 min) go to a Runner; no big-context agent waits on a job | `.friday/active/harness/rules/monitoring.md` |

> [!WARNING]
> **Rules 10 and 14 vary per project.** Both are gated on this project's
> `ACCELERATORS_ENABLED` setting, and since this guide is shared verbatim
> across every friday project, it can't tell you which form yours has —
> check `.friday/active/harness/harness.md` directly. When no accelerator hardware is
> configured, Rule 10 is a removed placeholder (kept numbered so the rest
> of the list doesn't shift between projects) and Rule 14 is reserved for
> a project-specific rule you can add later. When this project does have
> accelerator hardware, Rule 10 is the real GPU-allocation rule (detail:
> `.friday/active/harness/rules/gpu.md`) and Rule 14 covers shared-compute etiquette,
> written in during setup.
