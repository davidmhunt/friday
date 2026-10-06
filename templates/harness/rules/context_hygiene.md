# Context Hygiene (harness rule 17 — full text)

Read at session start by any role that reads files or runs commands.

**Why.** Every turn re-reads the whole context, so cost grows roughly with
context size × turns — quadratically over a long session. In the incident
behind this rule ~94% of an overnight run's cost was context re-reads; one
worker session ran 100–230 turns and grew from ~28k to 400–630k tokens.
Long contexts also degrade quality. Output tokens were ~5%. Keep context
small and sessions short.

## Reading

- **Locate, then read a range.** `grep -n` / `rg -n` for the symbol, then
  `sed -n 'A,Bp'` or Read with `offset`/`limit`. No whole-file `cat`/Read of
  a large file (more than ~300 lines) — read the function, not the module.
- **Don't re-read** a file already in your context unless it changed.
- **Never Read images, session transcripts, or saved tool-result dumps**
  unless the task is about that very image or file. Describe via metadata
  (size, `file`, a targeted `grep`) instead.
- **Prior work: read only what you need.** For other directives, closed
  directives, and `review/` files, `grep` for the ID or heading and read that
  section. Never read them whole "for context"; the Log's latest handoff
  entry plus your Step is the context.

## Command output

- Filter build/test output: `cmd 2>&1 | tail -n 40`, or
  `| grep -E 'error|FAIL|warning'`.
- For long logs, redirect to a file (`cmd > out.log 2>&1`), then `grep` or
  `tail` the file. Never print a full log into your context.
- Cap listings and dumps: `| head -n 50`, `wc -l` first, `--stat` not full
  output.

## Reviewing diffs

`git diff --stat A B` first; then diff per file (`git diff A B -- <file>`)
only for files that matter, and range-limit large ones. Don't dump
`git diff A B -- <dir>` repeatedly.

## Budget

If your context passes ~150k tokens, finish the current step (or reach a
clean stopping point), write a handoff in the directive's `## Log` (done,
commit hash, what is next), report, and end. A fresh agent continues from
the Log — that is cheaper than carrying the history. Controllers: restart or
`/compact` between directives; state lives in `status.md` and the directive
files, not in your context.
