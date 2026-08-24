#!/usr/bin/env python3
"""Automated open-access PDF discovery for docs/references/references.bib.

Run by the Researcher before hand-flagging a source in
docs/references/needs_pdf.md (see harness/roles/researcher.md "Tooling").
For every bib entry missing a `file` field, tries — in order, all free,
no-auth APIs — to find and download a legitimately open copy:

  1. Unpaywall (https://unpaywall.org)   — by DOI. Aggregates publisher OA,
     including IEEE/ACM hybrid-OA agreements, and OA repository mirrors.
  2. Semantic Scholar Graph API          — by DOI, falling back to a title
     search if there's no DOI. Surfaces `openAccessPdf` directly and also
     exposes an ArXiv id via `externalIds` when one exists.
  3. arXiv API                           — direct title search, for
     preprint mirrors of IEEE/ACM/journal papers not caught above.

This covers ACM and arXiv copies generically (DOI-based OA lookups don't
care which publisher issued the DOI) rather than needing a separate
per-publisher carve-out.

This is the automated, unattended-safe tier only. It never touches
institutional/library credentials — it only ever fetches what a given
service already publishes as open. Papers this script can't resolve stay
on the manual list (needs_pdf.md `Open` section); pulling those via a
personal institutional login (Google Scholar / EZproxy) is a supervised,
browser-driven action for a live session, not something this script does.

Downloads verified copies into docs/references/<bibkey>.pdf, records the
`file` field in-place in references.bib (surgical edit — leaves every
other entry's formatting untouched), and reconciles needs_pdf.md via
intake_references.sync_needs_pdf (same reconciliation the inbox-intake
flow uses).

Usage:
    python3 harness/tools/find_open_access_pdf.py            # all entries missing a PDF
    python3 harness/tools/find_open_access_pdf.py somekey ... # just these keys

Exit code: 0 always (this is a best-effort discovery pass, not a gate);
prints a RESOLVED / STILL OPEN summary.
Stdlib only, except for network calls via urllib (no third-party deps).
"""

import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from intake_references import parse_bib, sync_needs_pdf  # noqa: E402
from _config import user_agent  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
REFS_DIR = REPO_ROOT / "docs" / "references"
BIB_PATH = REFS_DIR / "references.bib"

USER_AGENT = user_agent()
TIMEOUT = 15
REQUEST_DELAY = 0.4  # be polite to free APIs


def _get(url: str, accept: str | None = None) -> bytes | None:
    headers = {"User-Agent": USER_AGENT}
    if accept:
        headers["Accept"] = accept
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.read()
    except Exception:
        return None


def normalize_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", title.lower())


def titles_match(a: str, b: str) -> bool:
    na, nb = normalize_title(a), normalize_title(b)
    if not na or not nb:
        return False
    return na == nb or na in nb or nb in na


def try_unpaywall(doi: str) -> str | None:
    url = f"https://api.unpaywall.org/v2/{urllib.parse.quote(doi)}?email={CONTACT_EMAIL}"
    raw = _get(url)
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    loc = data.get("best_oa_location") or {}
    return loc.get("url_for_pdf") or loc.get("url")


def try_semantic_scholar(doi: str | None, title: str | None) -> str | None:
    fields = "title,openAccessPdf,externalIds,isOpenAccess"
    if doi:
        url = f"https://api.semanticscholar.org/graph/v1/paper/DOI:{urllib.parse.quote(doi)}?fields={fields}"
        raw = _get(url, accept="application/json")
        if raw:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                data = {}
            hit = _pdf_from_s2_record(data)
            if hit:
                return hit
    if title:
        url = (
            "https://api.semanticscholar.org/graph/v1/paper/search"
            f"?query={urllib.parse.quote(title)}&fields={fields}&limit=3"
        )
        raw = _get(url, accept="application/json")
        if raw:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                data = {}
            for record in data.get("data", []):
                if titles_match(title, record.get("title", "")):
                    hit = _pdf_from_s2_record(record)
                    if hit:
                        return hit
    return None


def _pdf_from_s2_record(record: dict) -> str | None:
    oa = record.get("openAccessPdf") or {}
    if oa.get("url"):
        return oa["url"]
    arxiv_id = (record.get("externalIds") or {}).get("ArXiv")
    if arxiv_id:
        return f"https://arxiv.org/pdf/{arxiv_id}.pdf"
    return None


def try_arxiv(title: str | None) -> str | None:
    if not title:
        return None
    query = f'ti:"{title}"'
    url = f"http://export.arxiv.org/api/query?search_query={urllib.parse.quote(query)}&max_results=3"
    raw = _get(url)
    if not raw:
        return None
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return None
    ns = {"a": "http://www.w3.org/2005/Atom"}
    for entry in root.findall("a:entry", ns):
        entry_title_el = entry.find("a:title", ns)
        entry_title = (entry_title_el.text or "").strip() if entry_title_el is not None else ""
        if not titles_match(title, entry_title):
            continue
        id_el = entry.find("a:id", ns)
        if id_el is None or not id_el.text:
            continue
        arxiv_id = id_el.text.rstrip("/").rsplit("/", 1)[-1]
        return f"https://arxiv.org/pdf/{arxiv_id}.pdf"
    return None


def download_pdf(url: str) -> bytes | None:
    raw = _get(url, accept="application/pdf")
    if raw and raw[:5] == b"%PDF-" and len(raw) > 2000:
        return raw
    return None


def add_file_field(text: str, key: str, rel_path: str) -> str | None:
    pattern = re.compile(rf"(@\w+\s*\{{\s*{re.escape(key)}\s*,.*?)\n\}}", re.DOTALL)
    match = pattern.search(text)
    if not match:
        return None
    new_block = match.group(1) + f"\n  file = {{{rel_path}}},\n}}"
    return text[: match.start()] + new_block + text[match.end() :]


def resolve_entry(entry: dict) -> str | None:
    doi = entry.get("doi")
    title = entry.get("title")
    for finder, arg in (
        (try_unpaywall, doi),
        (try_semantic_scholar, (doi, title)),
        (try_arxiv, title),
    ):
        if finder is try_semantic_scholar:
            candidate = finder(*arg)
        else:
            if not arg:
                continue
            candidate = finder(arg)
        time.sleep(REQUEST_DELAY)
        if not candidate:
            continue
        pdf_bytes = download_pdf(candidate)
        if pdf_bytes:
            return candidate, pdf_bytes
    return None


def main() -> int:
    if not BIB_PATH.exists():
        print(f"No references file at {BIB_PATH} — nothing to do.")
        return 0

    text = BIB_PATH.read_text()
    entries = parse_bib(text)
    only_keys = set(sys.argv[1:]) or None

    targets = [e for e in entries if not e.get("file") and (only_keys is None or e["key"] in only_keys)]
    if not targets:
        print("No PDF-less entries to search for.")
        return 0

    resolved, still_open = [], []
    for entry in targets:
        key = entry["key"]
        result = resolve_entry(entry)
        if not result:
            still_open.append(key)
            print(f"[OPEN]     {key}: no OA copy found via Unpaywall/Semantic Scholar/arXiv")
            continue
        source_url, pdf_bytes = result
        dest = REFS_DIR / f"{key}.pdf"
        dest.write_bytes(pdf_bytes)
        rel_path = str(dest.relative_to(REPO_ROOT))
        new_text = add_file_field(text, key, rel_path)
        if new_text is None:
            still_open.append(key)
            print(f"[ERROR]    {key}: downloaded PDF but could not locate its bib entry to record `file` — left unresolved")
            dest.unlink(missing_ok=True)
            continue
        text = new_text
        resolved.append((key, source_url))
        print(f"[RESOLVED] {key}: {source_url} -> {rel_path}")

    if resolved:
        BIB_PATH.write_text(text)

    needs_pdf_notes = sync_needs_pdf(parse_bib(text))
    for note in needs_pdf_notes:
        print(f"  - {note}")

    print(f"\n{len(resolved)} resolved, {len(still_open)} still open (needs_pdf.md / manual/institutional fetch).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
