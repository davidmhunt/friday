# Document Budgets & Concision (harness rule 16 — full text)

Read when drafting, editing, or reviewing any prose deliverable under
`docs/` — theory documents, reports, memos, stage summaries — or when a
budget check fails.

## Why this rule exists

Every rule in this harness exists because of a real incident; this is
this one's. In the project this rule originated in, a phase produced a
technically excellent 41-page theory document that its own reader could not
learn from, and abandoned it in favour of a 17-page blog post covering
strictly more ground. The post-mortem found the mechanism, and it is a
harness defect, not an authoring one:

1. **Every quality gate measured correctness; none measured length or
   clarity.** A Reviewer could return NOT NOMINAL for a dropped term, a
   broken citation, or a build warning. There was no verdict available for
   "this is five pages and should be one." Length was the single free
   variable in a system with heavy pressure on it.
2. **Review was structurally additive.** Every finding across two dozen
   directives of record added a clause, a ledger row, or a qualifier. None
   ever removed one. Individually justified increments compounded into
   pages of accumulated assumptions and a multi-page digression on a term
   that was negligible in most configurations.
3. **Agents could self-check correctness but never comprehension.** The loop
   optimized the half it could close itself.

The counterweights below are therefore mechanical, not exhortative. "Write
concisely" is an instruction with no gate, and instructions without gates
erode.

## The invariant

**A prose deliverable's page budget is a Verify criterion with the same
force as a citation check.** Over budget is a defect with a standard
remedy, not a stylistic observation.

## Planner — opening a directive

Every directive producing a prose deliverable states, in its `Verify:`
block:

- **`Budget: <N> pp core body`** — the page count of the core document,
  excluding appendices and front/back matter.
- **`Appendix budget: <M> pp`** — default `≤ 50%` of the core budget.

A directive with a prose deliverable and no budget line is malformed; the
Reviewer rejects it back to the Planner rather than inventing one.

Budgets come from the phase spec in `docs/specs/`, where one exists. Set
them from what the material actually needs by comparison to a real
exemplar, never by estimating from the outline — outlines systematically
underestimate.

## Authoring roles (Researcher, Coder, Author) — while drafting

- **Core body carries the essential derivation only.** Full proofs, error
  analyses, and edge-case discussion go to an appendix in the same document,
  or to a separate supplemental document. When a core section threatens the
  budget, splitting it out is the *first* remedy considered, not the last.
- **Assumptions are stated inline where first used**, plus at most one
  summary table capped at **8 rows** per document. A running ledger that
  accretes a row per review pass is the specific pattern this forbids.
- **Every core concept gets a figure or a plot.** A core section that
  explains a concept with no visual is a review finding. Figures are
  routinely the most-praised element of a technical document and are the
  cheapest density-per-page available.
- **Cite a real bibliography entry for every citable step.**
- Where a phase defines a **style exemplar** (an approved short document in
  the target register), later documents are written to match its register,
  and the Reviewer diffs against it.

## Editor — the subtractive pass (mandatory before close)

No prose deliverable closes without an Editor pass. See
`.friday/active/harness/roles/editor.md`. In brief: the Editor's **only**
output is deletions, consolidations, and moves-to-appendix. It reports
`cut X lines / Y pages, math unchanged` and is scored on what it removed.
It may not add explanatory prose — that is the additive bias this pass
exists to counterweight.

If an Editor pass finds nothing to cut on a document that is within budget,
that is a valid result; it says so and closes.

## Cold-reader check (utility spawn — no role registration)

The Reviewer dispatches a **plain utility subagent** (deliberately *not* a
harness role, so it inherits no project context) with the document and
nothing else, asking for: what it understood, where it bogged down, and
which paragraphs it would cut.

It must be spawned with **no prior conversation context** — that is the
entire point, and it is why the Reviewer cannot perform this check itself
after having just verified the document. Its report goes to the user
alongside the directive verdict; it is **advisory input, never an
automatic edit** to the document.

## Reviewer — closing a directive

Add to the existing `[DONE]` checks, for any directive with a prose
deliverable:

1. **Budget check (mechanical, blocking).** `pdfinfo <doc>.pdf | grep Pages`
   for LaTeX, or a line count for Markdown. Over the stated budget →
   **NOT NOMINAL**, with the standard remedy named (move material to an
   appendix or a supplemental, or cut).
2. **Editor pass ran**, and its `cut X lines / Y pages` report is cited in
   the close-out record.
3. **Cold-reader check ran**, and its report is attached to the verdict.
4. **Assumption table ≤ 8 rows**; every core concept has a figure.

Findings that *add* text are still legitimate — a missing scope clause is a
real defect. But a review pass that nets positive lines on an at-budget
document must say so explicitly and name what it cut to make room. The
budget does not move to accommodate a finding; the document does.

## What this rule does NOT do

- It does not lower the correctness bar. Every correctness gate this
  harness already carries — citations, notation-as-macros, independent
  re-derivation, mechanical citation tools — stands unchanged.
- It does not apply to code, tests, logs, or history files.
- It does not apply to append-only records (`status_history.md`,
  `plans/history.md`), which are governed by rule 8 instead.
