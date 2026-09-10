# <Name> spec — scope, implementation goals, test plan

**Status: draft | signed off <YYYY-MM-DD> | superseded by `<slug>`**

<One paragraph: what this spec covers and who executes it. Note that this
file is the versioned source of truth, and that the Planner distills it into
`.friday/active/harness/plans/goals.md` — which is NOT version-controlled,
so this is the copy that survives.>

Prior work: <links to the previous phase's closeout/retro, or "none">.

---

## 1. Objective

<**The user's intent, refined by the Architect into agent-legible terms and
confirmed by the user.** Not a transcript and not a paraphrase-in-passing: a
deliberate translation into the register the Planner, Coder, Researcher and
Reviewer actually consume — concrete nouns for deliverables, named and
located external sources, and no vague qualifier left unmeasured (push
"clean", "simple", "similar to X" into §5's thresholds or §6's criteria).

The user's original framing is preserved verbatim in the Origin appendix at
the bottom of this file, so the translation stays auditable. **The refined
version must be confirmed by the user before the spec leaves draft** — an
unconfirmed translation is a guess wearing a spec's formatting.>

### 1.1 Restated as a closing condition

<One sentence: "This closes when ___." Concrete enough that its truth is
checkable by someone who wasn't in the conversation. If there is a register
or scale target (page counts, latency, accuracy), state it with the
comparison that justifies it.>

---

## 2. Scope

### In scope

<Numbered. Each item is a thing that will exist when this is done.>

### Explicitly out of scope

<Blunt. This list does real work — it is what stops a phase from drifting.
Include the tempting adjacent work and say why it's excluded, and where it
goes instead (a later phase, a stretch goal, dropped).>

---

## 3. Specification

<What is being built or derived, concretely enough that someone could
disagree with it. Tables over prose. For prose deliverables, every document
gets a **page budget** here — rule 16 makes it a blocking Verify criterion,
so a deliverable without one is malformed. For code, this is where module
layout, interfaces, and data contracts belong. Name concrete parameter
values and cite where they came from.>

---

## 4. Implementation goals

<Ordered `G0, G1, ...`, each independently checkable, each destined to
become a directive. State the dependency structure explicitly — what gates
what, and which chains are strict.

The rule worth remembering: **a goal not attached to a directive does not
happen.** Anything described here as "obviously needed" but left unscheduled
will still be undone at the next closeout.>

| # | Goal | Done when |
|---|---|---|
| **G0** | | |

---

## 5. Test plan

<Pin down, at minimum:
- **The unit of verification** — an assertion, a notebook, a test suite, a
  measured number against a derived closed form?
- **Tiers**: what runs on every commit vs. on demand vs. before a close.
- **Ground truth**: how do you know the right answer? (Simulation with
  planted values usually beats "it looks right".)
- **Acceptance thresholds**: specific numbers, set BEFORE implementation.
  Mark them as proposals until the user confirms them. This is the single
  highest-value part of the document — a measured result with no pre-agreed
  tolerance turns into a debate instead of a verdict.
- **Regression**: what stops a silent break, and what runs it?>

---

## 6. Success criteria

### 6.1 Must

<The phase does not close without these. Specific enough that a closeout
can state plainly which were met and which were not.>

### 6.2 Stretch

<Nice, not gating. Keeping these separate is what lets the must-list stay
honest.>

---

## 7. Open questions / resolved decisions

<Start as questions; convert to dated resolutions as the user rules on
them, keeping the reasoning. A resolved question with its rationale is worth
more later than a clean list of decisions.>

---

## 8. Carried-forward debt — rulings

<Every open item inherited from prior work gets an explicit **schedule** or
**drop**, in a table. No item may be left unruled: silence is how debt
survives a phase boundary intact.>

| Item | Ruling |
|---|---|

---

## 9. How we'll work

<Process constraints specific to this phase — the counterweights to whatever
went wrong last time. Anything mechanical here should be reflected in a
harness rule, and the rule named, so the spec and the harness agree rather
than drifting apart.>

---

## Appendix — Origin

<The user's original framing, verbatim, dated. This is the provenance record
for §1's refined objective: it is what was actually asked for, in the words
it was asked in, so a later reader can check the translation rather than
trust it. Never edited after the fact — corrections belong in Amendments.>

---

## Amendments

<Dated, appended, never a silent rewrite. Each entry: what changed, why, and
who asked for it.>
