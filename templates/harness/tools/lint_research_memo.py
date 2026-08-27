#!/usr/bin/env python3
"""Structural + Sources-format check for docs/research/*.md memos.

Run by the Reviewer alongside verify_references.py whenever the Researcher
produced or edited a memo this cycle (.friday/active/harness/roles/reviewer.md "Pass
protocol" step 5). Checks each memo against the shape defined in
.friday/active/harness/templates/research_memo_template.md:

  - The seven required `## ` section headers are present, in order:
    Question as asked, TL;DR, Evidence, Applicability to <project>,
    Recommended Experiment, Confidence, Sources. (Evidence may contain any
    number of `###` subsections — those aren't checked.)
  - The Sources section has exactly one bullet per cited bib key, each
    matching:
        - `bibkey` — Author(s) (Year), "Title," *Venue*. doi:...
        - `bibkey` — Author(s) (Year), "Title," *Venue*. url:...
        - `bibkey` — Author(s) (Year), "Title," *Venue*. file-only (docs/references/bibkey.pdf)
    (no `[1]`-style numbering, no grouping two keys on one line, no bare
    links to the .bib file).
  - Every bib key in Sources actually exists in
    docs/references/references.bib (mechanical existence only — content
    verification is still the Reviewer's WebFetch pass, not this script).

This is a WARN-style structural check, not a content check — it catches
format drift, not bad science. Exit code: 0 if no FAILs, 1 if any FAIL
(warnings don't block). Stdlib only.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from intake_references import parse_bib  # noqa: E402
from _config import PROJECT_NAME, find_repo_root  # noqa: E402

REPO_ROOT = find_repo_root()
RESEARCH_DIR = REPO_ROOT / "docs" / "research"
BIB_PATH = REPO_ROOT / "docs" / "references" / "references.bib"

REQUIRED_HEADERS = [
    "Question as asked",
    "TL;DR",
    "Evidence",
    f"Applicability to {PROJECT_NAME}",
    "Recommended Experiment",
    "Confidence",
    "Sources",
]

HEADER_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
SOURCE_LINE_RE = re.compile(
    r"^-\s+`([^`]+)`\s+—\s+.+?\.\s+(doi:\S+|url:\S+|file-only\s+\(docs/references/[^)]+\.pdf\))\s*$"
)


def find_section(text: str, name: str) -> tuple[int, int] | None:
    """Return (start, end) char offsets of the body of `## name`, or None."""
    pattern = re.compile(rf"^##\s+{re.escape(name)}\s*$", re.MULTILINE)
    m = pattern.search(text)
    if not m:
        return None
    start = m.end()
    next_h2 = re.search(r"^##\s+", text[start:], re.MULTILINE)
    end = start + next_h2.start() if next_h2 else len(text)
    return start, end


def check_memo(path: Path, bib_keys: set[str]) -> list[tuple[str, str]]:
    results = []
    text = path.read_text()

    top_headers = [h for h in HEADER_RE.findall(text)]
    present_required = [h for h in top_headers if h in REQUIRED_HEADERS]
    missing = [h for h in REQUIRED_HEADERS if h not in top_headers]
    if missing:
        results.append(("FAIL", f"{path.name}: missing required section(s): {', '.join(missing)}"))
    elif present_required != REQUIRED_HEADERS:
        results.append(
            ("FAIL", f"{path.name}: required sections out of order — found {present_required}")
        )
    else:
        results.append(("PASS", f"{path.name}: all required sections present and ordered"))

    sources_span = find_section(text, "Sources")
    if sources_span is None:
        results.append(("FAIL", f"{path.name}: no Sources section to check"))
        return results

    body = text[sources_span[0] : sources_span[1]]
    bullet_lines = [l for l in body.splitlines() if l.strip().startswith("-")]
    if not bullet_lines:
        results.append(("WARN", f"{path.name}: Sources section has no bullet lines"))

    seen_keys: dict[str, int] = {}
    for line in bullet_lines:
        m = SOURCE_LINE_RE.match(line.rstrip())
        if not m:
            results.append(("FAIL", f"{path.name}: malformed Sources line: {line.strip()!r}"))
            continue
        key = m.group(1)
        seen_keys[key] = seen_keys.get(key, 0) + 1
        if key not in bib_keys:
            results.append(("FAIL", f"{path.name}: Sources cites `{key}`, not found in references.bib"))

    for key, count in seen_keys.items():
        if count > 1:
            results.append(("FAIL", f"{path.name}: `{key}` appears {count} times in Sources (one bullet per key)"))

    if not any(status == "FAIL" for status, _ in results):
        results.append(("PASS", f"{path.name}: Sources section format OK ({len(seen_keys)} keys)"))

    return results


def main() -> int:
    bib_keys = {e["key"] for e in parse_bib(BIB_PATH.read_text())} if BIB_PATH.exists() else set()

    if not RESEARCH_DIR.is_dir():
        print(f"No {RESEARCH_DIR} — nothing to lint.")
        return 0

    memos = sorted(p for p in RESEARCH_DIR.glob("*.md") if p.name != "README.md")
    targets = [RESEARCH_DIR / a for a in sys.argv[1:]] if len(sys.argv) > 1 else memos
    if not targets:
        print("No memos to lint.")
        return 0

    all_results = []
    for memo in targets:
        if not memo.is_file():
            print(f"[FAIL] {memo}: not found")
            all_results.append(("FAIL", str(memo)))
            continue
        all_results.extend(check_memo(memo, bib_keys))

    for status, detail in all_results:
        print(f"[{status}] {detail}")

    fails = sum(1 for status, _ in all_results if status == "FAIL")
    warns = sum(1 for status, _ in all_results if status == "WARN")
    print(f"\n{len(all_results)} checks: {len(all_results) - fails - warns} PASS, {warns} WARN, {fails} FAIL")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
