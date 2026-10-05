# State files: `log.md` and `status_history.md`

What `log.md` and `status_history.md` are for, where `status_history.md` lives, and the two hazards of harness state living in a submodule. Back to the [User Guide](../USER_GUIDE.md).

`.friday/active/harness/log.md` is easy to skim past in the status table
([User Guide, Where things live](../USER_GUIDE.md#where-things-live)) but carries more than one row's worth of weight:

**`.friday/active/harness/log.md`** is the durable "why" behind the rule set itself —
seeded at setup, append-only. Every rule in `.friday/active/harness/harness.md` exists
because of a real incident, and this is where that incident is recorded:
what went wrong, which rule was added or amended in response, and when.
It's not a work log for directives (that's `status_history.md`, below) —
it's specifically the provenance trail for the harness's own rules. Read
it when you're wondering *why* a rule is phrased the way it is, or before
proposing to relax one — the harness's own convention (`.friday/active/harness/harness.md`
§ "Shared rules") is that a rule is never relaxed without a dated entry
here explaining why it's now safe to. `log.md` always lives in gitignored
`.friday/active/` — unlike `status_history.md` below, its location doesn't
depend on this project's tracker.

**`status_history.md`** is the append-only permanent record of every
directive that's ever been closed: closing date, tracker issue (if any),
the evidence the Reviewer checked, and the git commit hash that recorded
the work. It's what makes `.friday/active/harness/status.md` self-pruning —
Rule 3 ([rules.md](rules.md)) requires a directive's row to move out of `status.md` and into
`status_history.md` in the same pass that closes it, so `status.md` only
ever shows what's still open. `status_history.md` is exempt from the line
caps in Rule 8/[rules.md](rules.md) (it's a permanent record, not a hot-path file) — expect
it to just keep growing, and treat it as the place to answer "when was
this actually closed, and what commit proved it" without reconstructing
the answer from git log.

**Where `status_history.md` actually lives depends on whether this project
has a task tracker configured**, and that is not a stylistic choice — it's
what keeps a project's record of finished work from silently disappearing:

- **With a tracker configured** (`TRACKER_KIND` is `gitlab-issues` or
  `github-issues`), the closed issue/MR is itself a durable, externally
  hosted record, so `status_history.md` lives at
  `.friday/active/harness/status_history.md` alongside the rest of the
  harness's generated state — gitignored, tracked by neither this project
  repo nor `.friday` itself. Treat it as a convenience index, not a source
  of truth: the record a future reader should trust is the commit message
  ([hooks.md](hooks.md) above, and the "Attribution format" section of
  `.friday/active/harness/rules/version_control.md`) and the tracker issue.
- **With no tracker** (`TRACKER_KIND=none`, the interview's default), there
  is nothing else durable to fall back on, so `status_history.md`
  materializes at `docs/status_history.md` **in this project repo**
  instead — owner `project`, always tracked, never gitignored. It genuinely
  is the source of truth for this project, and a Reviewer commit that
  updates it belongs in the same commit as the work it describes.
  `init_harness.py` refuses to proceed if it ever finds `TRACKER_KIND=none`
  with `status_history.md` resolved into the gitignored location — that
  combination would mean a closed directive's only record vanishes on a
  fresh clone, which is exactly the failure mode this split exists to
  prevent.

Either way, the token to look for in role docs and other harness prose is
`STATUS_HISTORY_PATH` — it always points at whichever of the two applies to
this project, so you never need to hardcode one path or the other.

**Two hazards, both a consequence of harness state living inside a submodule
working tree:**

- **`git clean -xfd` run inside `.friday/` destroys all harness state.**
  `.friday/active/` is gitignored *within the submodule*, so `-x` (which
  sweeps up ignored files, not just untracked ones) removes it along with
  any other harness-side scratch output — `status.md`, `log.md`, the
  `plans/` goals and directive files, and (tracker-configured projects only)
  `status_history.md`. There is no undo. This is a real risk specifically
  because `cd .friday && git clean -xfd` to tidy a stray artifact sweeps
  `active/` up too.
- **`.friday/active/` is invisible to `git grep` and to a plain `rg`.**
  `git grep` doesn't look inside a submodule without `--recurse-submodules`,
  and `rg` honours `.friday/.gitignore`, which excludes `active/`. Finding
  nothing for a string you know is in `status.md` or a directive is not
  evidence it isn't there: use `rg --no-ignore` (or `rg -uu`), or
  `grep -r` pointed at `.friday/active/`.
