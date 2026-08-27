#!/usr/bin/env python3
"""Unit tests for check_commit_msg.py, via the real `commit-msg` wrapper.

Covers both checks the hook performs:
  1. the pre-existing 'Role: description' first-line check (unchanged
     behavior for non-Reviewer commits), and
  2. the new Reviewer-only body check (directive reference + tracker
     reference), added because v0.13.0 moved harness state out of the
     consumer repo — the Reviewer's commit message is now the only durable
     carrier of why a close-out happened (see version_control.md.tmpl,
     "What the Reviewer commits").

Tests invoke the actual `commit-msg` bash wrapper as a subprocess (the way
`git commit` really reaches this hook), not `check_commit_msg.py` directly —
that's the only way to honestly assert the advisory contract: the WARN text
is what changes between cases, but the process exit code must be 0 in every
single case, because commit-msg is symlinked straight into
`.git/hooks/commit-msg` and a blocking hook here would strand an agent
mid-migration with no escape hatch (see both hooks' docstrings).
"""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).parent
WRAPPER_SOURCE = HOOKS_DIR / "commit-msg"
CHECK_SOURCE = HOOKS_DIR / "check_commit_msg.py"


def _build_repo(tmp_path: Path) -> Path:
    """Minimal git repo with the wrapper + check script installed under
    .claude/hooks/, mirroring how a consumer project's MANIFEST.json wires
    these adapters up."""
    repo = tmp_path / "consumer"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)

    hooks_dir = repo / ".claude" / "hooks"
    hooks_dir.mkdir(parents=True)
    shutil.copy(CHECK_SOURCE, hooks_dir / "check_commit_msg.py")
    wrapper = hooks_dir / "commit-msg"
    shutil.copy(WRAPPER_SOURCE, wrapper)
    wrapper.chmod(0o755)

    return repo


def _run(repo: Path, body: str) -> subprocess.CompletedProcess:
    msg_file = repo / "COMMIT_EDITMSG"
    msg_file.write_text(body)
    wrapper = repo / ".claude" / "hooks" / "commit-msg"
    return subprocess.run(
        [str(wrapper), str(msg_file)],
        cwd=repo,
        capture_output=True,
        text=True,
    )


def test_valid_reviewer_message_passes_with_no_warn(tmp_path):
    repo = _build_repo(tmp_path)
    result = _run(
        repo,
        "Reviewer: close directive D-12, verify eval provenance\n\n"
        "Directive: D-12\nTracker: #123\n",
    )
    assert result.returncode == 0
    assert "WARN" not in result.stdout


def test_reviewer_message_missing_directive_is_flagged(tmp_path):
    repo = _build_repo(tmp_path)
    result = _run(
        repo,
        "Reviewer: close the open review item\n\n"
        "Closes #123\n",
    )
    assert result.returncode == 0  # advisory: never blocks
    assert "directive reference" in result.stdout


def test_reviewer_message_missing_tracker_is_flagged(tmp_path):
    repo = _build_repo(tmp_path)
    result = _run(
        repo,
        "Reviewer: close directive D-12, verify eval provenance\n\n"
        "Directive: D-12\n",
    )
    assert result.returncode == 0  # advisory: never blocks
    assert "tracker reference" in result.stdout


def test_no_code_changes_and_no_tracker_literal_passes(tmp_path):
    repo = _build_repo(tmp_path)
    result = _run(
        repo,
        "Reviewer: close directive D-12, no code changes\n\n"
        "Directive: D-12\nno tracker\n",
    )
    assert result.returncode == 0
    assert "WARN" not in result.stdout


def test_non_reviewer_message_unaffected(tmp_path):
    repo = _build_repo(tmp_path)
    result = _run(
        repo,
        "Coder: implement incremental state update in the core pipeline\n",
    )
    assert result.returncode == 0
    assert "WARN" not in result.stdout


def test_directive_and_tracker_only_in_git_comment_block_does_not_count(tmp_path):
    # Git appends a trailing '#'-prefixed comment block (diff summary etc.)
    # to the commit-msg file; a reference that only appears there was never
    # actually written by the committer and must not count as a pass.
    repo = _build_repo(tmp_path)
    result = _run(
        repo,
        "Reviewer: close directive, verify eval provenance\n\n"
        "# Please enter the commit message for your changes. Lines starting\n"
        "# with '#' will be ignored, and an empty message aborts the commit.\n"
        "#\n"
        "# Directive: D-12\n"
        "# Tracker: #123\n"
        "# On branch main\n"
        "# Changes to be committed:\n"
        "#\tmodified:   foo.py\n",
    )
    assert result.returncode == 0  # advisory: never blocks
    assert "directive reference" in result.stdout
    assert "tracker reference" in result.stdout


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
