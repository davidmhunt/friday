#!/usr/bin/env python3
"""Unit + regression tests for check_md_hygiene.py.

The regression case (test_symlinked_invocation_finds_real_repo_root) is the
whole point: check_md_hygiene.py is only ever reached in a consumer project
through a symlink (.claude/hooks/check_md_hygiene.py ->
.friday/adapters/hooks/check_md_hygiene.py). A test that imports/invokes the
file directly would pass even with the old `Path(__file__).resolve().
parents[2]` bug, because there'd be no symlink indirection to expose it —
that's exactly how the bug shipped silently. So this test builds a temp repo
with a real symlink layout mirroring MANIFEST.json and invokes the hook
*through the symlink*, as a subprocess, the way Claude Code / Antigravity
actually do.
"""

import subprocess
import sys
from pathlib import Path

import pytest

from check_md_hygiene import FILE_CAPS, PER_ENTRY_FILE

HOOK_SOURCE = Path(__file__).parent / "check_md_hygiene.py"


def _build_consumer_repo(tmp_path: Path) -> Path:
    """Build a minimal consumer repo tree:

        tmp_path/consumer/
            harness.config.env          <- marks this as the repo root
            harness/status.md           <- deliberately over its 150-line cap
            <every other FILE_CAPS/PER_ENTRY_FILE path>  <- empty stub, so
                only status.md's over-cap WARN fires by default
            .friday/adapters/hooks/check_md_hygiene.py   <- the real file
            .claude/hooks/check_md_hygiene.py            <- symlink -> above

    Returns the consumer repo root.
    """
    repo = tmp_path / "consumer"
    repo.mkdir()

    (repo / "harness.config.env").write_text("PROJECT_NAME=Test\n")

    harness_dir = repo / "harness"
    harness_dir.mkdir()
    # 151 lines: one line over the 150-line cap for harness/status.md.
    (harness_dir / "status.md").write_text("\n".join(f"line {i}" for i in range(151)) + "\n")

    # Every other configured path must exist too, or the "path not found"
    # WARN added for the missing-path case would fire here and pollute the
    # existing tests' output assertions. Stub them out empty (well under cap).
    for rel_path in {*FILE_CAPS, PER_ENTRY_FILE} - {"harness/status.md"}:
        stub = repo / rel_path
        stub.parent.mkdir(parents=True, exist_ok=True)
        stub.write_text("")

    real_hooks_dir = repo / ".friday" / "adapters" / "hooks"
    real_hooks_dir.mkdir(parents=True)
    real_hook = real_hooks_dir / "check_md_hygiene.py"
    real_hook.write_text(HOOK_SOURCE.read_text())

    symlink_hooks_dir = repo / ".claude" / "hooks"
    symlink_hooks_dir.mkdir(parents=True)
    symlink_hook = symlink_hooks_dir / "check_md_hygiene.py"
    symlink_hook.symlink_to(real_hook)

    return repo


def test_symlinked_invocation_finds_real_repo_root(tmp_path):
    """The exact bug: invoking through .claude/hooks/<symlink> must still
    resolve REPO_ROOT to the consumer repo, inspect harness/status.md there,
    and WARN + exit 1 because it's over cap. Before the fix, `.resolve()`
    followed the symlink into .friday/adapters/hooks, `parents[2]` landed on
    .friday/, harness/status.md wasn't found there, and the hook silently
    exited 0 with no output.
    """
    repo = _build_consumer_repo(tmp_path)
    symlink_hook = repo / ".claude" / "hooks" / "check_md_hygiene.py"

    result = subprocess.run(
        [sys.executable, str(symlink_hook)],
        cwd=repo,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1, (
        f"expected exit 1 (over-cap warning), got {result.returncode}. "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "WARN | hygiene | harness/status.md is 151 lines (cap 150)" in result.stdout


def test_symlinked_invocation_under_cap_exits_zero(tmp_path):
    """Sanity counterpart: same symlink layout, but status.md is under cap
    -> no WARN, exit 0. Confirms the fix doesn't just always warn."""
    repo = _build_consumer_repo(tmp_path)
    (repo / "harness" / "status.md").write_text("short file\n")
    symlink_hook = repo / ".claude" / "hooks" / "check_md_hygiene.py"

    result = subprocess.run(
        [sys.executable, str(symlink_hook)],
        cwd=repo,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_missing_configured_path_warns_but_stays_advisory(tmp_path):
    """A FILE_CAPS entry that doesn't exist (relocated file, typo'd path)
    used to be silently skipped, so the cap silently stopped being enforced.
    It must now WARN — but must not flip the exit code, since a mid-
    migration project must not have commits blocked by this."""
    repo = _build_consumer_repo(tmp_path)
    (repo / "harness" / "status.md").write_text("short file\n")
    # Remove a FILE_CAPS entry that _build_consumer_repo otherwise stubs out,
    # simulating a relocated/mistyped configured path.
    (repo / "docs" / "references" / "needs_pdf.md").unlink()
    symlink_hook = repo / ".claude" / "hooks" / "check_md_hygiene.py"

    result = subprocess.run(
        [sys.executable, str(symlink_hook)],
        cwd=repo,
        capture_output=True,
        text=True,
    )

    assert "WARN | hygiene | configured path not found: docs/references/needs_pdf.md" in result.stdout
    assert result.returncode == 0


def test_direct_invocation_without_symlink_still_works(tmp_path):
    """The direct (non-symlinked) case should also work correctly, since
    find_repo_root() tries cwd first regardless of how the file is reached."""
    repo = _build_consumer_repo(tmp_path)
    real_hook = repo / ".friday" / "adapters" / "hooks" / "check_md_hygiene.py"

    result = subprocess.run(
        [sys.executable, str(real_hook)],
        cwd=repo,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "WARN | hygiene | harness/status.md is 151 lines (cap 150)" in result.stdout


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
