#!/usr/bin/env python3
"""Mechanical markdown-hygiene checker (harness.md rule 8).

Checks the hot-path markdown files against line-count caps and prints a WARN
line per violation. Plain Python, no dependencies — the Controller runs it
at session start, the Reviewer at close-out, and a warn-only pre-commit hook
on every commit.

Exit code: 1 if any file is over its cap, 0 otherwise. The pre-commit wrapper
ignores the code (always exits 0) so hygiene never blocks a commit; the
Controller/Reviewer treat exit 1 as the signal to compact per rule 8.

CONFIGURE: FILE_CAPS below is the authoritative copy of the caps quoted in
.friday/active/harness/rules/md_hygiene.md — keep the two in sync.

NOTE: don't derive the consumer repo root from `Path(__file__).resolve()` —
this module is reached via a symlink (.claude/hooks/<this file> ->
.friday/templates/adapters/hooks/<this file> in a consumer project), and
`.resolve()` follows the symlink to its real path inside `.friday/`, making
an ancestor count land inside the submodule instead of the consumer repo
(see .friday/active/harness/tools/_config.py for the same note). Search upward instead — from
cwd first, then from the *unresolved* `Path(__file__).parent` as a fallback
— for a directory containing `harness.config.env`, or failing that one
containing both `.gitmodules` and `.friday/`. Kept as a tiny standalone
reader rather than importing `_config.py` or `check_agent_spawn.py`'s
`_load_high_tier_keywords()` — this module is deliberately dependency-free
so it stays exercisable in isolation (see module docstring above).
"""

import sys
from pathlib import Path


def _looks_like_consumer_root(candidate: Path) -> bool:
    if (candidate / "harness.config.env").exists():
        return True
    return (candidate / ".gitmodules").exists() and (candidate / ".friday").is_dir()


def find_repo_root() -> Path:
    """Consumer repo root, found by an upward search — NOT derived from a
    resolved `__file__` (see module docstring: this file is reached via a
    symlink, and `.resolve()` points inside `.friday/`, not the consumer
    repo). Tries cwd first (these hooks are documented/invoked from the
    repo root), then falls back to walking up from the *unresolved*
    `Path(__file__).parent` (i.e. following the symlink's own directory,
    not its resolved target) in case cwd isn't the repo root.
    """
    for start in (Path.cwd(), Path(__file__).parent):
        for candidate in (start, *start.parents):
            if _looks_like_consumer_root(candidate):
                return candidate
    return Path.cwd()


REPO_ROOT = find_repo_root()

# Path (relative to repo root) -> max line count. History files are
# append-only permanent records and are intentionally exempt — don't add them.
FILE_CAPS = {
    ".friday/active/harness/status.md": 150,
    ".friday/active/harness/plans/goals.md": 120,
}

# Each OPEN directive file is capped individually. Closed directives live in
# plans/directives/closed/ (not matched by this glob) and are exempt, as
# append-only records; TEMPLATE.md is not a directive.
DIRECTIVE_GLOB = ".friday/active/harness/plans/directives/*.md"
DIRECTIVE_CAP = 200
DIRECTIVE_SKIP = {"TEMPLATE.md"}


def count_lines(path: Path) -> int:
    with path.open("r", encoding="utf-8", errors="replace") as f:
        return sum(1 for _ in f)


def main() -> int:
    any_warn = False
    for rel_path, cap in FILE_CAPS.items():
        path = REPO_ROOT / rel_path
        if not path.exists():
            # A missing configured path used to be silently skipped, which
            # meant a relocated or mistyped path quietly stopped being
            # enforced — invisible in every channel, since the pre-commit
            # wrapper always exits 0. WARN instead, but stay advisory: don't
            # flip any_warn, since a missing file isn't an over-cap file and
            # this hook must not start blocking commits during a migration.
            print(f"WARN | hygiene | configured path not found: {rel_path}")
            continue
        n = count_lines(path)
        if n > cap:
            print(f"WARN | hygiene | {rel_path} is {n} lines (cap {cap})")
            any_warn = True

    for path in sorted(REPO_ROOT.glob(DIRECTIVE_GLOB)):
        if path.name in DIRECTIVE_SKIP:
            continue
        n = count_lines(path)
        if n > DIRECTIVE_CAP:
            rel = path.relative_to(REPO_ROOT).as_posix()
            print(f"WARN | hygiene | {rel} is {n} lines (cap {DIRECTIVE_CAP})")
            any_warn = True

    return 1 if any_warn else 0


if __name__ == "__main__":
    sys.exit(main())
