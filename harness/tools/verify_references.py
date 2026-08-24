#!/usr/bin/env python3
"""Mechanical existence check for docs/references/references.bib.

Run by the Reviewer during the research-memo verification step
(harness/roles/reviewer.md). For each BibTeX entry:

  - has `doi`  -> checks https://doi.org/<doi> resolves
  - elif `url` -> checks that URL resolves
  - elif `file`-> checks the referenced local PDF exists on disk
  - else       -> WARN: no verifiable field

This proves the source EXISTS (a link resolves, a file is present). It does
NOT prove the fetched content actually supports the claim it's cited for —
that half stays a WebFetch + human/agent read, per harness/roles/reviewer.md.

Exit code: 0 if no FAILs (WARNs don't block), nonzero if any FAIL.
Stdlib only — no third-party bibtex parser dependency, so this runs
anywhere Python 3 does.
"""

import re
import sys
import urllib.request
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _config import user_agent, find_repo_root  # noqa: E402

REPO_ROOT = find_repo_root()
BIB_PATH = REPO_ROOT / "docs" / "references" / "references.bib"
TIMEOUT = 10
USER_AGENT = user_agent()

ENTRY_RE = re.compile(r"@\w+\s*\{\s*([^,\s]+)\s*,(.*?)\n\}", re.DOTALL)
FIELD_RE = re.compile(r"(\w+)\s*=\s*[{\"](.*?)[}\"]\s*,?\s*$", re.MULTILINE)


def parse_bib(text: str) -> list[dict]:
    entries = []
    for match in ENTRY_RE.finditer(text):
        key, body = match.group(1), match.group(2)
        fields = {"key": key}
        for fmatch in FIELD_RE.finditer(body):
            fields[fmatch.group(1).strip().lower()] = fmatch.group(2).strip()
        entries.append(fields)
    return entries


def check_url(url: str, is_doi: bool = False) -> tuple[bool, str]:
    headers = {
        "User-Agent": USER_AGENT,
    }
    if is_doi:
        headers["Accept"] = "application/vnd.citationstyles.csl+json"
    req = urllib.request.Request(url, method=("GET" if is_doi else "HEAD"), headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return 200 <= resp.status < 400, f"HTTP {resp.status}"
    except urllib.error.HTTPError as e:
        if e.code == 405:  # some hosts reject HEAD; retry GET
            try:
                req2 = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
                with urllib.request.urlopen(req2, timeout=TIMEOUT) as resp:
                    return 200 <= resp.status < 400, f"HTTP {resp.status} (GET fallback)"
            except Exception as e2:
                return False, f"GET fallback failed: {e2}"
        return False, f"HTTP {e.code}"
    except Exception as e:
        return False, str(e)


def check_entry(entry: dict) -> tuple[str, str]:
    key = entry.get("key", "?")
    if entry.get("file"):
        path = REPO_ROOT / entry["file"]
        if path.is_file():
            return "PASS", f"{key}: file -> exists ({entry['file']})"
    if entry.get("doi"):
        ok, detail = check_url(f"https://doi.org/{entry['doi']}", is_doi=True)
        if ok:
            return "PASS", f"{key}: doi -> {detail}"
        # If doi check had an issue, try url fallback if available
        if entry.get("url"):
            ok_u, detail_u = check_url(entry["url"])
            if ok_u:
                return "PASS", f"{key}: url fallback -> {detail_u}"
        return "FAIL", f"{key}: doi -> {detail}"
    if entry.get("url"):
        ok, detail = check_url(entry["url"])
        return ("PASS" if ok else "FAIL"), f"{key}: url -> {detail}"
    if entry.get("file"):
        path = REPO_ROOT / entry["file"]
        ok = path.is_file()
        return ("PASS" if ok else "FAIL"), f"{key}: file -> {'exists' if ok else f'MISSING at {path}'}"
    return "WARN", f"{key}: no doi/url/file field — nothing to verify"


def main() -> int:
    if not BIB_PATH.exists():
        print(f"No references file at {BIB_PATH} — nothing to verify.")
        return 0

    entries = parse_bib(BIB_PATH.read_text())
    if not entries:
        print(f"{BIB_PATH} has no parsable entries.")
        return 0

    results = [check_entry(e) for e in entries]
    for status, detail in results:
        print(f"[{status}] {detail}")

    fails = sum(1 for status, _ in results if status == "FAIL")
    warns = sum(1 for status, _ in results if status == "WARN")
    print(f"\n{len(entries)} entries: {len(entries) - fails - warns} PASS, {warns} WARN, {fails} FAIL")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
