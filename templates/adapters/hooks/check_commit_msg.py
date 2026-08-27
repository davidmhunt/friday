#!/usr/bin/env python3
"""Mechanical commit-message-prefix checker (harness.md rule 12).

Checks that a commit message's first line matches `Role: description`
(capitalized role, colon, space, non-empty description). Plain Python, no
dependencies — meant to run from a warn-only `commit-msg` hook.

Advisory only: it prints a violation line, and the wrapper always exits 0, so
a non-conforming message is never rejected. It exists to catch drift while
never flagging a human's own commits, merges, or autosquash commits.

A second, Reviewer-specific check runs only when the first line's role is
`Reviewer`: since v0.13.0 moved harness state into `.friday/active/` (a
different repo the consumer project never tracks), a `Reviewer:` commit's
message is the only durable carrier of *why* the close-out happened — the
directive it closes and the tracker issue it resolves. See
`.friday/active/harness/rules/version_control.md` ("What the Reviewer
commits") for the authoritative format. This check reads the WHOLE message
body (not just line 1) and, per git convention, ignores any line starting
with `#` — git appends its own instructional comment block (diff summary,
branch info) to the commit-msg file, and a directive/tracker reference that
only appears inside that block was never actually written by the committer.

Both checks stay advisory: they print a WARN line, and the wrapper always
exits 0, so a non-conforming message is never rejected. `commit-msg` is
symlinked straight into `.git/hooks/commit-msg`, so a blocking check here
would strand an agent mid-migration with no escape hatch — same advisory
philosophy as check_md_hygiene.py's pre-commit hook.

Exit code: 1 if flagged, 0 otherwise (the wrapper ignores this).

CONFIGURE: ROLE_PREFIX_RE if your role names differ. DIRECTIVE_RE and
TRACKER_RE are deliberately permissive (see their comments) and deliberately
do NOT read harness.config.env — this hook is the one with zero config
dependency, so it always works the same way regardless of whether a project
has a tracker configured. Accept the literal `no tracker` unconditionally
and let the role docs (reviewer.md.tmpl) say which applies to a given
project.
"""

import re
import sys

ROLE_PREFIX_RE = re.compile(r"^(Controller|Planner|Coder|Runner|Reviewer|Author|Researcher|Harness): .+")

# Never flagged: merge commits and fixup!/squash! autosquash commits.
EXEMPT_PREFIXES = ("Merge ", "fixup!", "squash!")

# Directive reference: either an explicit "Directive: <id>" line/field, or an
# inline "directive <id>" mention anywhere in the body (case-insensitive on
# the word "directive" — commit prose varies). IDs look like `D-12`,
# `2026-08-26-a`, or a bare slug like `gpu-sweep`: word characters, digits,
# and hyphens, no whitespace.
DIRECTIVE_RE = re.compile(r"(?i)\bdirective[:\s]+([A-Za-z0-9][A-Za-z0-9-]*)")

# Tracker reference: GitHub/GitLab-style `#123`, GitLab MR-style `!45`,
# Jira-style `ABC-12`, or the literal `no tracker` for projects with no
# tracker configured (this hook never reads config to decide which applies).
TRACKER_RE = re.compile(r"(?:#\d+|!\d+|\b[A-Z][A-Z0-9]+-\d+\b|\bno tracker\b)")


def is_exempt(first_line: str) -> bool:
    return first_line.startswith(EXEMPT_PREFIXES)


def check(first_line: str) -> bool:
    """True if the line is flagged (violates the convention)."""
    if is_exempt(first_line):
        return False
    return not ROLE_PREFIX_RE.match(first_line)


def strip_git_comments(body: str) -> str:
    """Drop every line starting with `#` — git's own trailing comment block
    (diff summary, branch/status info) that a real committer never wrote.
    A directive/tracker reference that only appears there must not count."""
    return "\n".join(
        line for line in body.splitlines() if not line.lstrip().startswith("#")
    )


def check_reviewer_body(body: str) -> list[str]:
    """Reviewer-only check. Returns a list of missing-piece descriptions
    (empty list means the body is fine). `body` should already have git's
    comment lines stripped."""
    missing = []
    if not DIRECTIVE_RE.search(body):
        missing.append("directive reference ('Directive: <id>' or 'directive <id>')")
    if not TRACKER_RE.search(body):
        missing.append("tracker reference ('#123', '!45', 'ABC-12', or 'no tracker')")
    return missing


def main() -> int:
    if len(sys.argv) < 2:
        return 0  # no commit-msg file path given

    try:
        with open(sys.argv[1], "r", encoding="utf-8", errors="replace") as f:
            raw = f.read()
    except OSError:
        return 0  # unreadable — fail open

    first_line = raw.split("\n", 1)[0].rstrip("\n")

    if not first_line.strip() or first_line.startswith("#"):
        return 0  # empty/comment-only message: git will abort anyway

    flagged = False

    if check(first_line):
        print(
            f"WARN | commit-msg | first line does not match 'Role: description' "
            f"(harness rule 12): {first_line!r}"
        )
        flagged = True

    if first_line.startswith("Reviewer: "):
        body = strip_git_comments(raw)
        missing = check_reviewer_body(body)
        for item in missing:
            print(
                f"WARN | commit-msg | Reviewer commit missing {item} "
                f"(.friday/active/harness/rules/version_control.md): {first_line!r}"
            )
        if missing:
            flagged = True

    return 1 if flagged else 0


if __name__ == "__main__":
    sys.exit(main())
