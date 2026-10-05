# Giving input to agents, and invoking roles directly

How to supply literature, data and steering, how to invoke the Researcher and Author yourself, and the validation commands. Back to the [User Guide](../USER_GUIDE.md).

## A. Providing Literature & Research Papers

Projects that use the Researcher role maintain a strict, verified bibliography workflow in `docs/references/`:

1. **Drop files in the inbox**: Place raw PDFs (any filename) and `.bib` files (e.g., from Zotero or Google Scholar) into:
   ```
   docs/references/inbox/
   ```
2. **Process the inbox**: Run the reference intake tool (or ask the Researcher/Controller to run it):
   ```bash
   python3 .friday/active/harness/tools/intake_references.py
   ```
   - Automatically merges entries into `docs/references/references.bib` without duplicates.
   - Moves and renames PDFs to `docs/references/<bibkey>.pdf`.
   - Clears the inbox staging area.
3. **Monitor missing PDFs**: Check `docs/references/needs_pdf.md` for any citations currently missing a local PDF copy.

> [!WARNING]
> Sources listed under "Confirmed unavailable" in `docs/references/needs_pdf.md` are uncitable. Do not cite papers that cannot be verified against a readable PDF.


## B. Providing Experimental Data & Traces

- Place raw sensor logs, datasets, or benchmark traces wherever this project keeps its data (see `AGENTS.md` § Repository Layout).
- **Rule 1 & Rule 6 (Data Artifacts)**: Canonical datasets must not be overwritten destructively. Always take a pre-mutation snapshot before transforming or modifying data.


## C. Providing Guidance, Steering, & Suggestions

- **Ideas, bugs, new work**: tell the Controller. It turns them into a goal for the Planner (or a trivial one-step directive) and brings you the proposal to approve. There is no suggestions inbox to edit by hand.
- **Answering open questions**: a directive's `## Open questions` section is meant to be answered — reply to the Controller, or write your answer inline in the directive file and tell the Controller to re-read it.
- **Real-time steering during Controller execution**:
  When a Controller session is running, you can reply directly with feedback. The Controller will tag your instructions with `User-Feedback:` and relay them to subagents, ensuring binding steering.

## D. Invoking the Researcher and Author directly

The usual route to the Researcher and Author is through the Controller
("have the Researcher look into …", "have the Author fold core-03 in"). Two
situations are common enough to invoke them yourself instead:

**Researcher, directly** — when you have a standalone question that isn't
yet worth a full directive: "does the literature support this modeling
choice", "find prior work on X before we commit to an approach". Prompt
it directly:

```
You are the researcher agent. Please research <topic> and produce a formal memo in docs/research/.
```

For a quick single-fact lookup that doesn't need the full memo + Reviewer
citation-check pipeline, ask for a quick lookup: under Antigravity that is
the lighter `researcher-quick` agent; under Claude Code the Researcher is
spawned with a light-tier model for it. Reserve the full Researcher for
anything a directive will actually depend on.

**Author, directly** — after a Reviewer pass closes a real milestone (a
new version, a finalized result, a systemic bug fix, a real ablation) and
you want that reflected in the project's persistent record right away:

```
You are the author agent. Please fold the <milestone> the reviewer just closed into docs/RESULTS.md.
```

If this project's LaTeX/Beamer drafting suite is enabled, the same prompt
pattern applies to building `docs/report/` from Researcher-drafted theory
and Reviewer-verified results. Remember Author's boundary from [User Guide, Roles and tiers](../USER_GUIDE.md#roles-and-tiers): it only
ever touches the docs/results/report surface, never source code or the
role working-state namespaces.

## E. Validation commands

Run these from the repo root:

```bash
# Check markdown line caps on status.md, goals.md and open directives (Rule 8)
python3 .claude/hooks/check_md_hygiene.py   # or .agents/hooks/check_md_hygiene.py

# Verify that all citations in references.bib have valid DOIs or local PDFs
python3 .friday/active/harness/tools/verify_references.py

# Check that no document cites confirmed-unavailable sources
python3 .friday/active/harness/tools/check_unavailable_sources.py

# Lint formatting of research memos
python3 .friday/active/harness/tools/lint_research_memo.py <memo_file>.md

# Process new references and PDFs in the inbox
python3 .friday/active/harness/tools/intake_references.py
```
