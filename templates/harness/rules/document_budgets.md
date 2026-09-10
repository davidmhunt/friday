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

### The measurement is fixed, and it is not argued

A budget whose measurement can move is not a budget. Both halves of the
measurement — how much is counted, and how much fits on a page — are pinned
here, and neither is a lever a role may pull to make a number pass.

**1. "Core body" has exactly one definition, emitted by a tool.**

- **Markdown:** everything from the first `##` heading through the end of
  the last content section. A title/date/path block above the first `##` is
  **front matter**; a trailing `## Sources` / `## References` block is
  **back matter**. Both are excluded. The lint tool emits the authoritative
  number and that is what the Reviewer checks — no role counts by hand.
- **LaTeX:** `pdfinfo <doc>.pdf | grep Pages`, built from committed sources.

**2. Layout lengths are frozen. They are not a way to fit a budget.**

Float spacing, caption skips, and list/bibliography item separation live in
the shared preamble at fixed values and **may not be adjusted to make a
document fit**. Tightening whitespace makes the page count pass while the
prose grows — the count stays mechanical, but the thing it counts stops
being length. A document that does not fit at the frozen lengths **is over
budget**: cut it, or amend the budget through the Architect.

*Both clauses exist because of one incident. A phase's style exemplar met
its 3 pp budget twice by pulling the same three spacing levers while its
body prose grew ~10%; the second pull exhausted them, and the drafter's own
disclosure — not any gate — is what surfaced it. In the same phase, two
roles spent a full review cycle disputing whether a five-line header counted
toward a line budget, with both readings defensible from what was then
written.*

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

### Quoted source text is immutable under trimming

**No trimming pass may alter quoted material — ever, by anyone.** Not the
Editor, not the author trimming their own draft, not a fix pass after a
review bounce. Trimming removes whole units: sentences, clauses, list items,
table rows. A quotation is not a unit that may be shortened, elided,
paraphrased, or re-punctuated to save a line.

If a document cannot meet its budget without touching a quote, it is over
budget. The remedy is to cut surrounding prose, drop the claim the quote
supports, or amend the budget through the Architect — never to compress the
evidence.

*Exists because a memo whose entire evidentiary warrant was "every claim
carries a verbatim quote" was found to contain a quotation with two terms
silently dropped; during the fix pass for that defect, budget pressure
nearly produced a second altered quote in a different source, caught only by
the author's own disclosure. A quote that is not verbatim converts a
document's warrant into a claim it cannot support, and the damage is
invisible to every mechanical check — the page and equation number still
exist, so only someone opening the source can see it.*

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
5. **Every post-draft edit is diffed, not reported.** For each commit that
   touched the document after its first draft — the Editor's pass *and* any
   author fix or trim pass — read the diff and confirm it is genuinely
   subtractive and that no quoted material changed. A role's own report that
   a pass was subtractive is not evidence; the diff is.
6. **Any edit after a verdict re-opens that verdict in full.** When a
   document is edited after you have verified it, your prior NOMINAL no
   longer applies to any part of it. Re-gate the whole artifact, not only
   the findings you raised — the edit had the run of the document, so the
   re-check must too. Verifying only your own findings is how a defect
   enters the half of the document nobody looked at twice.

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
