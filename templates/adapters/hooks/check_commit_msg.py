#!/usr/bin/env python3
"""Mechanical commit-message-prefix checker (harness.md rule 12).

Checks that a commit message's first line matches `Role: description`
(capitalized role, colon, space, non-empty description). Plain Python, no
dependencies — meant to run from a warn-only `commit-msg` hook.

Advisory only: it prints a violation line, and the wrapper always exits 0, so
a non-conforming message is never rejected. It exists to catch drift while
never flagging a human's own commits, merges, or autosquash commits.

Exit code: 1 if flagged, 0 otherwise (the wrapper ignores this).

CONFIGURE: ROLE_PREFIX_RE if your role names differ.
"""

import re
import sys

ROLE_PREFIX_RE = re.compile(r"^(Controller|Planner|Coder|Runner|Reviewer|Author|Researcher|Harness): .+")

# Never flagged: merge commits and fixup!/squash! autosquash commits.
EXEMPT_PREFIXES = ("Merge ", "fixup!", "squash!")


def is_exempt(first_line: str) -> bool:
    return first_line.startswith(EXEMPT_PREFIXES)


def check(first_line: str) -> bool:
    """True if the line is flagged (violates the convention)."""
    if is_exempt(first_line):
        return False
    return not ROLE_PREFIX_RE.match(first_line)


def main() -> int:
    if len(sys.argv) < 2:
        return 0  # no commit-msg file path given

    try:
        with open(sys.argv[1], "r", encoding="utf-8", errors="replace") as f:
            first_line = f.readline().rstrip("\n")
    except OSError:
        return 0  # unreadable — fail open

    if not first_line.strip() or first_line.startswith("#"):
        return 0  # empty/comment-only message: git will abort anyway

    if check(first_line):
        print(
            f"WARN | commit-msg | first line does not match 'Role: description' "
            f"(harness rule 12): {first_line!r}"
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
