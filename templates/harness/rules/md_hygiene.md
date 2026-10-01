# Markdown Hygiene (harness rule 8 — full text)

Read at a Controller session start, a Reviewer close-out, or when a hygiene
WARN fires.

Files every session reads stay lean; whoever next edits one over cap
compacts it in the same edit.

| File | Cap | How it stays under |
|------|-----|--------------------|
| `.friday/active/harness/status.md` | 150 lines | Holds only OPEN loops, directives, claims and live jobs; a closed directive's row moves to `status_history.md` (rule 3). Recent milestones: keep the last few, one line each. |
| `.friday/active/harness/plans/goals.md` | 120 lines | Objectives and standing context only, one line per fact. |
| each open `plans/directives/<ID>.md` | 200 lines | Log entries stay short: what, commit, a Verify excerpt. Long diagnosis goes to `review/` or the commit message and is linked. |

Append-only logs are **exempt**: `status_history.md`, `plans/history.md`,
`log.md`, and closed directives in `plans/directives/closed/`.

**Enforcement:** `.claude/hooks/check_md_hygiene.py` (or
`.agents/hooks/check_md_hygiene.py` under Antigravity) checks the caps above
— keep its `FILE_CAPS` in sync with this table. The Controller runs it at
session start and the Reviewer at close-out; the git `pre-commit` hook runs
it warn-only on every commit. A WARN that survives two close-outs goes in
the Reviewer's report to the Controller.
