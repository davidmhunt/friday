"""accept-01: accept and `accept --reject` exit 8 while tracked files are uncommitted."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_accept_gate import cli, finish_first, git, repo  # noqa: E402,F401

DIRECTIVE = "docs/directives/core-01.md"


@pytest.fixture
def review(repo):
    (repo / "board.txt").write_text("v1\n")
    git(repo, "add", "board.txt")
    git(repo, "commit", "--no-verify", "-qm", "add board")
    finish_first(repo)
    return repo


def snapshot(r):
    return (r / DIRECTIVE).read_text(), git(r, "rev-parse", "HEAD")


@pytest.mark.parametrize("flags", [[], ["--reject", "bad routing"]])
@pytest.mark.parametrize("staged", [False, True])
def test_dirty_tracked_file_blocks(review, flags, staged):
    r = review
    (r / "board.txt").write_text("v2\n")
    if staged:
        git(r, "add", "board.txt")
    before = snapshot(r)
    p = cli(r, "accept", "core-01", *flags)
    assert p.returncode == 8, p.stderr
    assert "board.txt" in p.stderr
    assert 'git commit -am "core-01: review changes" -m "Directive: core-01"' in p.stderr
    assert "friday accept core-01" in p.stderr
    assert snapshot(r) == before
    assert "Status: awaiting review" in before[0]


def test_untracked_files_do_not_block(review):
    (review / "scratch.txt").write_text("x\n")
    p = cli(review, "accept", "core-01")
    assert p.returncode == 0, p.stderr
    assert "Status: done" in (review / DIRECTIVE).read_text()


def test_accept_after_review_commit_and_commits_lists_it(review):
    r = review
    (r / "board.txt").write_text("v2\n")
    assert cli(r, "accept", "core-01").returncode == 8
    git(r, "commit", "--no-verify", "-am", "core-01: review changes", "-m", "Directive: core-01")
    p = cli(r, "accept", "core-01")
    assert p.returncode == 0, p.stderr
    assert "Status: done" in (r / DIRECTIVE).read_text()
    c = cli(r, "commits", "core-01")
    assert c.returncode == 0, c.stderr
    assert "core-01: review changes" in c.stdout
