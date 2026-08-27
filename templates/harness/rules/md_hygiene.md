# Markdown Hygiene (harness rule 8 — full text)

Read at Planner/Reviewer pass start or when a hygiene WARN fires.

Mandatory-read-every-pass files stay lean; whoever next edits one over cap
compacts it in the same edit. Suggested caps (adjust for your project; keep
an authoritative table somewhere mechanical if you build a checker):

- `.friday/active/harness/status.md` ≤150 lines — should rarely approach this, since it
  only ever holds OPEN directives + live jobs; a closed directive's row
  moves to `.friday/active/harness/status_history.md` (rule 3), not to a "resolved
  narrative" section
- `.friday/active/harness/plans/suggestions.md` ≤60, near-empty between planner passes
  (fold + delete, don't tag in place)
- `.friday/active/harness/plans/next_steps.md` ≤400 ("Resolved this cycle" pruned to
  one-line pointers once superseded)
- `.friday/active/harness/coding/tasks_working.md` ≤250
- `.friday/active/harness/coding/tasks_finished.md` ≤200 (current + prior cycle in full,
  older trimmed to `[hash] task — DONE`)
- `docs/references/needs_pdf.md` ≤150 (rows pruned automatically by
  `.friday/active/harness/tools/intake_references.py` as they resolve; a "Confirmed
  unavailable" row that's grown stale should be revisited, not just left)

History files (`.friday/active/harness/plans/history.md`, `.friday/active/harness/coding/history.md`,
`.friday/active/harness/status_history.md`) are append-only logs and EXEMPT from caps.

**Cleanup clause:** to prevent context bloat without breaking the planning
loop, the Reviewer should move closed tasks (`[DONE]`, `[REVIEWED]`) to
`.friday/active/harness/coding/tasks_finished.md` or `history.md`. Tasks may be left in the
working file only if they provide critical context needed to address
something in the immediate next planning cycle.

**Per-entry cap:** consider capping each `.friday/active/harness/coding/tasks_working.md`
task entry at a fixed line count (e.g. 12 lines) — status line + `Verify:`
excerpt + one-line pointers to the relevant review verdict and history
entry; detailed diagnosis/build detail goes only to those files, never
duplicated in the working-tasks entry.

**Enforcement:** `.agents/hooks/check_md_hygiene.py` (if Antigravity) or
`.claude/hooks/check_md_hygiene.py` (if Claude) checks the caps above — keep its
`FILE_CAPS` in sync with this file. Planner and Reviewer run it at pass start;
`.agents/hooks/pre-commit` (if Antigravity) or `.claude/hooks/pre-commit` (if
Claude) runs it warn-only on every commit once installed. A WARN surviving two
consecutive Planner/Reviewer passes becomes a Reviewer finding in
`.friday/active/harness/plans/suggestions.md`.
