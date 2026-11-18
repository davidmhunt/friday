# notes-01: `friday finish` keeps notes from breaking the Log (fixes #14)
Status: approved
Goal: field-fixes
Node: any
Deliverable: code
Land: goal
Verify: uv run --with pytest pytest -q tests/test_finish_notes.py && uv run --with pytest pytest -q && claude plugin validate .
Hardware: none

## Goal
`friday finish` copies `runs/<id>/notes.md` into the Log without ever producing a line that
`friday check` reads as a section: any line starting with `#` in the notes is demoted below the
Log's own levels. The implementer and runner guidance says not to write `## ` headings in notes.
tests/test_finish_notes.py proves a directive with headed notes still passes `friday check` and
`friday parse` after both `finish` and `finish --blocked`.

## Steps
1. bin/friday `cmd_finish`: before appending notes, rewrite each line matching `^#{1,6} ` to
   `#### ` plus the heading text (deeper levels stay at `######`), so no notes line starts with
   `## ` or `### `. Leave fenced code blocks in the notes untouched.
2. agents/implementer.md and agents/runner.md (and the execute workflow's measure-only wording if
   it describes notes): notes are plain lines or `- ` bullets, never `#` headings.
3. tests/test_finish_notes.py: notes with `# A`, `## Step 1: x`, `### B` and a fenced block
   containing `## not a heading`: after `finish` and after `finish --blocked`, `friday check` and
   `friday parse` pass, the headings appear demoted and the fenced block is unchanged.
   CHANGELOG in the 1.1.0 section (Fixed) naming #14.

## Out of scope
- Changing where notes live or whether finish copies them.

## Log
