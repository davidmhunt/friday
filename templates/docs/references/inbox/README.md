# Reference inbox

Drop new sources here as you find them — no need to organize before dropping:

- PDFs, any filename.
- BibTeX entries for them, in one or more `*.bib` files (a Zotero "Export
  Items -> BibTeX" dump works as-is).

The Researcher runs `.friday/active/harness/tools/intake_references.py` to process this
folder: it merges new entries into `docs/references/references.bib`
(skipping duplicates by DOI/key), renames + moves each matched PDF into
`docs/references/<bibkey>.pdf`, rewrites the entry's `file` field to point
there, and removes processed items from this folder. Anything it can't
resolve automatically (no matching PDF, a key collision, an entry with
neither `doi`/`url`/`file`) is left in place and flagged in its report —
fix flagged items and rerun, or hand them to the Researcher to sort out
manually.

This folder is a staging area, not permanent storage — everything in it
(other than this README) is gitignored and expected to be emptied out by
the intake script, not committed to.
