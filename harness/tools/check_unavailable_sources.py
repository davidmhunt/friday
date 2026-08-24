#!/usr/bin/env python3
"""Block citation of "Confirmed unavailable" sources in generated artifacts.

An entry lands in the "Confirmed unavailable" section of
docs/references/needs_pdf.md when neither automated OA discovery nor a real
manual/institutional attempt turned up a copy (see needs_pdf.md itself).
Since its content can never be reverified, David's rule is: it may stay in
references.bib for the record, but it must not be used as evidentiary
support anywhere — not in docs/theory/, docs/report/, or harness/research/.

This script:
  1. Parses the "Confirmed unavailable" bib keys out of needs_pdf.md.
  2. Looks each key up in references.bib to get its doi/url (citations in
     the wild sometimes link the DOI/URL directly instead of the bib key).
  3. Scans every docs/theory/**/*.tex, docs/report/**/*.tex, and
     harness/research/*.md file for:
       - LaTeX cite commands (comma-separated key lists)
       - a literal backtick-quoted key mention (the memo convention)
       - a markdown link whose target contains the key's doi/url
  4. Reports every hit as a violation (file:line, key).

Run by the Reviewer per harness/roles/reviewer.md whenever a memo, theory
doc, or report changes. Exit code: 0 if clean, 1 if any citation of a
confirmed-unavailable source is found. Stdlib only.
"""

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
REFS_DIR = REPO_ROOT / "docs" / "references"
NEEDS_PDF_PATH = REFS_DIR / "needs_pdf.md"
BIB_PATH = REFS_DIR / "references.bib"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from intake_references import parse_bib  # noqa: E402

UNAVAILABLE_HEADER_RE = re.compile(r"^## Confirmed unavailable", re.MULTILINE)
NEXT_HEADER_RE = re.compile(r"^## ", re.MULTILINE)
ROW_KEY_RE = re.compile(r"^- `([^`]+)`", re.MULTILINE)

CITE_RE = re.compile(r"\\cite[tp]?\{([^}]*)\}")

SCAN_GLOBS = [
    ("docs/theory", "**/*.tex"),
    ("docs/report", "**/*.tex"),
    ("harness/research", "*.md"),
]


def confirmed_unavailable_keys(text: str) -> set[str]:
    start = UNAVAILABLE_HEADER_RE.search(text)
    if not start:
        return set()
    rest = text[start.end():]
    end = NEXT_HEADER_RE.search(rest)
    section = rest[: end.start()] if end else rest
    return set(ROW_KEY_RE.findall(section))


def key_locators(keys: set[str], bib_entries: list[dict]) -> dict[str, list[str]]:
    """Map each unavailable key to the strings that identify it in prose (doi/url)."""
    by_key = {e["key"]: e for e in bib_entries}
    locators: dict[str, list[str]] = {}
    for key in keys:
        entry = by_key.get(key, {})
        vals = [key]
        if entry.get("doi"):
            vals.append(entry["doi"])
        if entry.get("url"):
            vals.append(entry["url"])
        locators[key] = vals
    return locators


def scan_file(path: Path, locators: dict[str, list[str]]) -> list[tuple[int, str, str]]:
    hits = []
    lines = path.read_text(errors="replace").splitlines()
    for lineno, line in enumerate(lines, start=1):
        found_keys = set()
        for m in CITE_RE.finditer(line):
            for k in m.group(1).split(","):
                found_keys.add(k.strip())
        for key, needles in locators.items():
            backtick_hit = f"`{key}`" in line
            doi_url_hit = any(n in line for n in needles[1:])
            if key in found_keys or backtick_hit or doi_url_hit:
                hits.append((lineno, key, line.strip()))
    return hits


def main() -> int:
    if not NEEDS_PDF_PATH.exists() or not BIB_PATH.exists():
        print("No needs_pdf.md / references.bib found — nothing to check.")
        return 0

    keys = confirmed_unavailable_keys(NEEDS_PDF_PATH.read_text())
    if not keys:
        print("No 'Confirmed unavailable' entries — nothing to check.")
        return 0

    bib_entries = parse_bib(BIB_PATH.read_text())
    locators = key_locators(keys, bib_entries)

    violations = 0
    for subdir, pattern in SCAN_GLOBS:
        base = REPO_ROOT / subdir
        if not base.is_dir():
            continue
        for path in sorted(base.glob(pattern)):
            for lineno, key, line in scan_file(path, locators):
                violations += 1
                rel = path.relative_to(REPO_ROOT)
                print(f"[FAIL] {rel}:{lineno}: cites confirmed-unavailable `{key}`: {line}")

    if violations:
        print(
            f"\n{violations} citation(s) of confirmed-unavailable sources found "
            f"({len(keys)} keys tracked). Remove the citation or replace it with "
            "a verifiable source — see docs/references/needs_pdf.md."
        )
        return 1

    print(f"Clean: no citations of the {len(keys)} confirmed-unavailable source(s) found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
