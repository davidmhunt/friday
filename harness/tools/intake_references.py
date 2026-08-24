#!/usr/bin/env python3
"""Merge new sources from docs/references/inbox/ into references.bib.

Run by the Researcher when David has dropped PDFs and/or a Zotero BibTeX
export into docs/references/inbox/ (see that folder's README). For each
entry found across the inbox's *.bib files:

  1. Skip it (leave in place, flag) if its key or DOI already exists in
     docs/references/references.bib — don't silently overwrite.
  2. Otherwise, try to resolve a PDF for it:
       - if the entry already has a `file` field, use that path (relative
         to the inbox or the repo root);
       - else look for an inbox PDF whose filename fuzzy-matches the entry
         key or title.
     A matched PDF is renamed to `<bibkey>.pdf` and moved into
     docs/references/; the entry's `file` field is (re)written to point
     there.
  3. Append the entry to references.bib and drop it from the inbox's
     working set. Entries with no doi/url/file and no resolvable PDF are
     left in the inbox and flagged rather than merged half-verifiable.

After merging, reconciles docs/references/needs_pdf.md against the full
bib: any entry that now has a `file` field has its row removed from the
"Open" section (it's resolved); any entry in references.bib that still has
no `file` field and isn't already tracked (Open or Confirmed unavailable)
gets a new "Open" row added, so nothing is silently missing a PDF with no
paper trail. It never removes a "Confirmed unavailable" row itself — that's
a human ruling, not a mechanical one.

Any inbox PDF that ends up matched to zero entries, and any entry that
can't be resolved, is reported and left in place for a human/Researcher
follow-up pass — this script never deletes or guesses past what it can
actually verify. Stdlib only, same constraint as verify_references.py.

Exit code: 0 if nothing was flagged, 1 if anything needed manual follow-up
(non-fatal — items were merged where possible either way).
"""

import re
import shutil
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _config import find_repo_root  # noqa: E402

REPO_ROOT = find_repo_root()
REFS_DIR = REPO_ROOT / "docs" / "references"
INBOX_DIR = REFS_DIR / "inbox"
BIB_PATH = REFS_DIR / "references.bib"
NEEDS_PDF_PATH = REFS_DIR / "needs_pdf.md"
NEEDS_PDF_ROW_RE = re.compile(r"^- `([^`]+)`")

ENTRY_RE = re.compile(r"@(\w+)\s*\{\s*([^,\s]+)\s*,(.*?)\n\}", re.DOTALL)
FIELD_RE = re.compile(r"(\w+)\s*=\s*[{\"](.*?)[}\"]\s*,?\s*$", re.MULTILINE)


def parse_bib(text: str) -> list[dict]:
    entries = []
    for match in ENTRY_RE.finditer(text):
        entry_type, key, body = match.group(1), match.group(2), match.group(3)
        fields = {"_type": entry_type, "key": key}
        for fmatch in FIELD_RE.finditer(body):
            fields[fmatch.group(1).strip().lower()] = fmatch.group(2).strip()
        entries.append(fields)
    return entries


def render_entry(entry: dict) -> str:
    lines = [f"@{entry['_type']}{{{entry['key']},"]
    for k, v in entry.items():
        if k in ("_type", "key"):
            continue
        lines.append(f"  {k} = {{{v}}},")
    lines.append("}")
    return "\n".join(lines)


def normalize_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", title.lower())


def words(s: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]{3,}", s.lower()))


def find_pdf_match(entry: dict, pdfs: list[Path]) -> Path | None:
    if entry.get("file"):
        candidate = Path(entry["file"])
        for base in (INBOX_DIR, REPO_ROOT):
            resolved = (base / candidate).resolve() if not candidate.is_absolute() else candidate
            if resolved.is_file():
                return resolved

    stem_norm = normalize_title(entry.get("key", ""))
    for pdf in pdfs:
        if normalize_title(pdf.stem) == stem_norm:
            return pdf

    # DOI suffix match (e.g. jcgm1002008e in doi)
    doi = entry.get("doi", "")
    if doi:
        doi_suffix = normalize_title(doi.split("/")[-1])
        if doi_suffix:
            for pdf in pdfs:
                if doi_suffix in normalize_title(pdf.stem):
                    return pdf

    title = entry.get("title", "")
    if title:
        title_norm = normalize_title(title)
        for pdf in pdfs:
            p_stem_norm = normalize_title(pdf.stem)
            if p_stem_norm and (p_stem_norm in title_norm or title_norm in p_stem_norm):
                return pdf

        # Word overlap heuristic for truncated titles / slight variations
        t_words = words(title)
        if t_words:
            best_pdf = None
            best_score = 0.0
            for pdf in pdfs:
                p_words = words(pdf.stem)
                overlap = p_words & t_words
                score = len(overlap) / len(t_words)
                if len(overlap) >= 3 and score > 0.4 and score > best_score:
                    best_score = score
                    best_pdf = pdf
            if best_pdf:
                return best_pdf

    # Author + Year match (e.g. Kalman1960 -> author kalman, year 1960)
    author = entry.get("author", "")
    year = entry.get("year", "")
    if author and year:
        first_author = normalize_title(author.split(",")[0].split()[0])
        if first_author:
            for pdf in pdfs:
                p_norm = normalize_title(pdf.stem)
                if first_author in p_norm and year in p_norm:
                    return pdf

    return None


def split_needs_pdf(text: str) -> tuple[list[str], list[str], list[str]]:
    """Split needs_pdf.md into (preamble, open_section, confirmed_section)
    lines, each section including its own '## ...' heading line."""
    lines = text.splitlines()
    open_idx = next((i for i, l in enumerate(lines) if l.strip() == "## Open"), None)
    confirmed_idx = next(
        (i for i, l in enumerate(lines) if l.strip().startswith("## Confirmed")), None
    )
    if open_idx is None or confirmed_idx is None:
        return lines, [], []
    return lines[:open_idx], lines[open_idx:confirmed_idx], lines[confirmed_idx:]


def row_keys(lines: list[str]) -> set[str]:
    return {m.group(1) for l in lines if (m := NEEDS_PDF_ROW_RE.match(l))}


def add_file_field(text: str, key: str, rel_path: str) -> str | None:
    pattern = re.compile(rf"(@\w+\s*\{{\s*{re.escape(key)}\s*,.*?)\n\}}", re.DOTALL)
    match = pattern.search(text)
    if not match:
        return None
    new_block = match.group(1) + f"\n  file = {{{rel_path}}},\n}}"
    return text[: match.start()] + new_block + text[match.end() :]


def sync_needs_pdf(all_entries: list[dict]) -> list[str]:
    """Reconcile docs/references/needs_pdf.md against the merged bib.
    Returns a list of human-readable notes about what changed."""
    if not NEEDS_PDF_PATH.exists():
        return []

    preamble, open_lines, confirmed_lines = split_needs_pdf(NEEDS_PDF_PATH.read_text())
    if not open_lines or not confirmed_lines:
        return []  # unexpected shape — don't guess, leave it for a human pass

    with_file = {e["key"] for e in all_entries if e.get("file")}
    open_heading, confirmed_heading = open_lines[0], confirmed_lines[0]
    open_rows = [l for l in open_lines if NEEDS_PDF_ROW_RE.match(l)]
    confirmed_keys = row_keys(confirmed_lines)

    notes = []

    # Drop resolved or confirmed rows from Open.
    kept_rows = []
    for l in open_rows:
        key = NEEDS_PDF_ROW_RE.match(l).group(1)
        if key in with_file:
            notes.append(f"needs_pdf.md: resolved, removed Open row for {key}")
        elif key in confirmed_keys:
            notes.append(f"needs_pdf.md: confirmed unavailable, removed Open row for {key}")
        else:
            kept_rows.append(l)
    open_rows = kept_rows

    # Add rows for anything now PDF-less and untracked.
    tracked = row_keys(open_rows) | confirmed_keys
    for e in all_entries:
        key = e.get("key")
        if not key or e.get("file") or key in tracked:
            continue
        title = e.get("title", "(no title)")
        locator = f"doi:{e['doi']}" if e.get("doi") else (f"url:{e['url']}" if e.get("url") else "no doi/url")
        open_rows.append(
            f"- `{key}` — \"{title}\" — {locator} — no PDF matched during intake — "
            f"flagged {date.today().isoformat()}"
        )
        notes.append(f"needs_pdf.md: added Open row for {key}")

    body = open_rows if open_rows else ["_(none)_"]
    open_lines = [open_heading, ""] + body + [""]

    if notes:
        NEEDS_PDF_PATH.write_text(
            "\n".join(preamble + open_lines + confirmed_lines) + "\n"
        )
    return notes


def main() -> int:
    existing_text = BIB_PATH.read_text() if BIB_PATH.exists() else ""
    existing = parse_bib(existing_text)

    if not INBOX_DIR.is_dir():
        print(f"No inbox at {INBOX_DIR} — nothing to merge.")
        for note in sync_needs_pdf(existing):
            print(f"  - {note}")
        return 0

    pdfs = sorted(INBOX_DIR.glob("*.pdf"))
    used_pdfs: set[Path] = set()
    merged, updated, skipped, flagged = [], [], [], []
    merged_entries: list[dict] = []

    inbox_bibs = sorted(INBOX_DIR.glob("*.bib"))
    existing_keys = {e["key"] for e in existing}
    existing_dois = {e["doi"].lower() for e in existing if e.get("doi")}

    for bib_path in inbox_bibs:
        entries = parse_bib(bib_path.read_text())
        remaining = []
        for entry in entries:
            key = entry["key"]
            doi = entry.get("doi", "").lower()
            if key in existing_keys or (doi and doi in existing_dois):
                skipped.append(f"{key}: already in references.bib (key or DOI match)")
                remaining.append(entry)
                continue

            pdf_match = find_pdf_match(entry, [p for p in pdfs if p not in used_pdfs])
            if pdf_match:
                dest = REFS_DIR / f"{key}.pdf"
                shutil.move(str(pdf_match), str(dest))
                used_pdfs.add(pdf_match)
                entry["file"] = str(dest.relative_to(REPO_ROOT))

            if not (entry.get("doi") or entry.get("url") or entry.get("file")):
                flagged.append(f"{key}: no doi/url, and no matching PDF found in inbox — left in {bib_path.name}")
                remaining.append(entry)
                continue

            existing_text += "\n" + render_entry(entry) + "\n"
            existing_keys.add(key)
            if doi:
                existing_dois.add(doi)
            merged_entries.append(entry)
            merged.append(f"{key}: merged" + (f" (PDF -> {entry['file']})" if pdf_match else " (doi/url only, no PDF)"))

        if remaining:
            bib_path.write_text(
                "\n".join(render_entry(e) for e in remaining) + "\n"
            )
        else:
            bib_path.unlink()

    # Now match any unused inbox PDFs against existing entries missing a file field
    all_entries = existing + merged_entries
    for entry in all_entries:
        if entry.get("file"):
            continue
        key = entry["key"]
        pdf_match = find_pdf_match(entry, [p for p in pdfs if p not in used_pdfs])
        if pdf_match:
            dest = REFS_DIR / f"{key}.pdf"
            shutil.move(str(pdf_match), str(dest))
            used_pdfs.add(pdf_match)
            rel_path = str(dest.relative_to(REPO_ROOT))
            entry["file"] = rel_path
            new_text = add_file_field(existing_text, key, rel_path)
            if new_text:
                existing_text = new_text
            updated.append(f"{key}: matched inbox PDF ({pdf_match.name}) -> {rel_path}")

    if merged or updated:
        BIB_PATH.write_text(existing_text)

    unused_pdfs = [p for p in pdfs if p not in used_pdfs]
    for p in unused_pdfs:
        flagged.append(f"{p.name}: no bib entry matched this PDF — left in inbox")

    needs_pdf_notes = sync_needs_pdf(all_entries)

    for label, items in (
        ("MERGED", merged),
        ("UPDATED EXISTING", updated),
        ("SKIPPED (duplicate)", skipped),
        ("FLAGGED", flagged),
        ("NEEDS_PDF.MD", needs_pdf_notes),
    ):
        if items:
            print(f"\n{label}:")
            for line in items:
                print(f"  - {line}")

    print(f"\n{len(merged)} merged, {len(updated)} updated with PDFs, {len(skipped)} duplicates skipped, {len(flagged)} flagged for follow-up.")
    return 1 if flagged else 0


if __name__ == "__main__":
    sys.exit(main())
