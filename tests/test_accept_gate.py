"""gate-01: `Accept: user` directives wait for `friday accept`."""
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CLI = ROOT / "bin" / "friday"
sys.path.insert(0, str(ROOT / "lib"))
import friday_core as fc  # noqa: E402

D1 = """# core-01: First
Status: approved
Goal: core
Node: any
Deliverable: code
Land: goal
Accept: user
Verify: true
Hardware: none

## Goal
First.

## Steps
1. Do it

## Out of scope
- nothing

## Review
- open a.txt and look for the word hello

## Log
"""
D2 = D1.replace("core-01: First", "core-02: Second").replace("Accept: user\n", "").replace(
    "## Review\n- open a.txt and look for the word hello\n\n", "").replace("First.", "Second.")
GOAL = """# core: Core
Status: approved
Base: main
Land: pr

## Goal
Core.

## Directives
1. core-01: First
2. core-02: Second

## Log
"""


def git(r, *a):
    return subprocess.run(["git", "-C", str(r), *a], capture_output=True, text=True, check=True).stdout


def cli(r, *a):
    return subprocess.run([sys.executable, str(CLI), *a], cwd=r, capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    r = tmp_path / "repo"
    (r / "docs/directives").mkdir(parents=True)
    (r / "docs/goals").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(r)], check=True)
    for k, v in (("user.name", "t"), ("user.email", "t@t")):
        git(r, "config", k, v)
    (r / "docs/directives/core-01.md").write_text(D1)
    (r / "docs/directives/core-02.md").write_text(D2)
    (r / "docs/goals/core.md").write_text(GOAL)
    git(r, "add", ".")
    git(r, "commit", "--no-verify", "-qm", "init")
    return r


def finish_first(r):
    assert cli(r, "start", "core-01").returncode == 0
    f = cli(r, "finish", "core-01")
    assert f.returncode == 0, f.stderr
    return f


def test_finish_with_accept_user_awaits_review(repo):
    f = finish_first(repo)
    t = (repo / "docs/directives/core-01.md").read_text()
    assert "Status: awaiting review" in t
    assert "- open a.txt and look for the word hello" in f.stdout
    assert "friday accept core-01" in f.stdout
    assert git(repo, "log", "-1", "--format=%s").strip() == "core-01: record results"


def test_finish_blocked_ignores_accept_user(repo):
    cli(repo, "start", "core-01")
    assert cli(repo, "finish", "core-01", "--blocked", "x").returncode == 0
    assert "Status: blocked: x" in (repo / "docs/directives/core-01.md").read_text()


def test_accept_marks_done_in_one_commit_with_later_directive_active(repo):
    finish_first(repo)
    # core-02 is active in this worktree (step 3 makes `friday start core-02` work here; set it up directly)
    fc.install_commit_hook(repo)
    fc.write_marker(repo, {"id": "core-02", "started": time.time(), "host": "h", "gate": False, "base": "x"})
    n0 = int(git(repo, "rev-list", "--count", "HEAD"))
    r = cli(repo, "accept", "core-01", "--note", "looks right")
    assert r.returncode == 0, r.stderr
    t = (repo / "docs/directives/core-01.md").read_text()
    assert "Status: done" in t and "Accepted by user: " in t and t.rstrip().endswith("looks right")
    assert int(git(repo, "rev-list", "--count", "HEAD")) == n0 + 1
    assert git(repo, "log", "-1", "--format=%s").strip() == "core-01: accepted"
    assert "Directive: core-01" in git(repo, "log", "-1", "--format=%B")


def test_accept_refuses_unless_awaiting_review(repo):
    r = cli(repo, "accept", "core-02")
    assert r.returncode == 1 and "not awaiting review" in r.stderr


def test_accept_refuses_off_the_goal_branch(repo):
    finish_first(repo)
    git(repo, "switch", "-q", "-c", "elsewhere")
    r = cli(repo, "accept", "core-01")
    assert r.returncode == 1 and "friday/core" in r.stderr
    assert "awaiting review" in (repo / "docs/directives/core-01.md").read_text()


def test_accept_reject_blocks(repo):
    finish_first(repo)
    r = cli(repo, "accept", "core-01", "--reject", "wrong colour")
    assert r.returncode == 0, r.stderr
    assert "Status: blocked: wrong colour" in (repo / "docs/directives/core-01.md").read_text()
    assert "Status: blocked: core-01" in (repo / "docs/goals/core.md").read_text()
