# notes-01: `friday finish` keeps notes from breaking the Log (fixes #14)
Status: done
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

### 2026-11-18
Commits:
- 61e222e finish: demote # headings in notes to #### so they cannot break the Log (#14)
- e4ce9fe agents: notes are plain lines or bullets, never # headings
- ecb4398 tests: finish with headed notes keeps check and parse passing; CHANGELOG (#14)
- d301487 finish/accept/unblock: find the Log end outside fenced blocks; execute workflow notes wording
Verify: Verify passed: uv run --with pytest pytest -q tests/test_finish_notes.py && uv run --with pytest pytest -q && claude plugin validate .
Independent review: gaps fixed in second review: 1. bin/friday:462 (cmd_finish), also :527 (cmd_accept) and :572 (cmd_unblock): Step 1 leaves fenced blocks untouched, so a fenced '## not a heading' line is now written into the Log. The code that finds the end of the Log, 're.search(r'(?m)^## ', ...)', ignores fences. The next finish, accept or unblock on that directive treats the fenced '## ' line as the end of the Log and inserts its new entry inside the previous entry's code fence. The parser in friday_core.py:240-244 does track fences, so it then reads the new entry as fenced text, not a Log entry. That means the notes still break the Log, which is what #14 was meant to stop. finish --blocked followed by unblock and a second finish is a normal path. The test only runs finish once, so it never hits this. (evidence: I copied the insertion logic into a script and ran it on a Log holding the blocked entry with the fenced '## not a heading'. Unblock's '### 2026-11-19 / Unblocked: ...' was inserted between the opening fence and '## not a heading', inside the code block.) 2. workflows/execute.js:190: Step 2 says to update the execute workflow's measure-only wording if it describes notes. It does: 'append your findings to 'runs/'{id}/notes.md' and do not commit'. That wording was not changed and still does not say to use plain lines or '- ' bullets with no '#' headings, so the implementer brief built at runtime gives no guidance against headings. (evidence: 'git show e4ce9fe' touches only agents/implementer.md and agents/runner.md. 'grep -n notes workflows/execute.js' shows line 190 with the unchanged wording.)
