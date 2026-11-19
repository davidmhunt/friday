"""tt-04: `friday approve --goal <g>` publishes the plan ref; the hook keeps it user-only.
Run: uv run --with pytest pytest -q tests/test_approve.py"""
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib"))
sys.path.insert(0, str(ROOT / "hooks"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import friday_hook as hook  # noqa: E402
from test_accept_gate import cli, git, repo  # noqa: E402,F401


@pytest.fixture
def planned(repo, tmp_path):
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
    git(repo, "remote", "add", "origin", str(origin))
    git(repo, "checkout", "-q", "-b", "friday/core")
    return repo, origin


def remote_refs(origin):
    out = subprocess.run(["git", "-C", str(origin), "for-each-ref", "--format=%(refname) %(objectname)"],
                         capture_output=True, text=True, check=True).stdout
    return dict(l.split() for l in out.splitlines())


def test_approve_pushes_both_refs(planned):
    r, origin = planned
    p = cli(r, "approve", "--goal", "core")
    assert p.returncode == 0, p.stderr
    refs = remote_refs(origin)
    head = git(r, "rev-parse", "HEAD").strip()
    assert refs["refs/heads/friday/core"] == head
    assert refs["refs/heads/friday-plan/core"] == head


def test_approve_refuses_dirty_tree(planned):
    r, origin = planned
    (r / "docs/goals/core.md").write_text((r / "docs/goals/core.md").read_text() + "\nx\n")
    p = cli(r, "approve", "--goal", "core")
    assert p.returncode == 8, p.stderr
    assert remote_refs(origin) == {}


def test_approve_refuses_check_errors(planned):
    r, origin = planned
    (r / "docs/directives/core-01.md").write_text("garbage\n")
    git(r, "commit", "--no-verify", "-qam", "break")
    p = cli(r, "approve", "--goal", "core")
    assert p.returncode == 1
    assert remote_refs(origin) == {}


def test_approve_refuses_non_fast_forward(planned):
    r, origin = planned
    git(r, "commit", "--no-verify", "-q", "--allow-empty", "-m", "more")
    assert cli(r, "approve", "--goal", "core").returncode == 0
    git(r, "reset", "-q", "--hard", "HEAD~1")
    git(r, "commit", "--no-verify", "-q", "--allow-empty", "-m", "diverge")
    before = remote_refs(origin)
    p = cli(r, "approve", "--goal", "core")
    assert p.returncode == 1
    assert "fast-forward" in p.stderr
    assert remote_refs(origin) == before


@pytest.mark.parametrize("cmd", [
    "friday approve --goal core",
    "python3 /x/bin/friday approve --goal core",
    "bash -c 'friday approve --goal core'",
    "ssh alfred 'cd w && friday approve --goal core'",
    "uv run bin/friday approve --goal core",
])
def test_hook_denies_approve(cmd):
    assert hook.check_accept(cmd)


@pytest.mark.parametrize("cmd", [
    "git push origin x:friday-plan/g",
    "git push origin HEAD:refs/heads/friday-plan/g",
    "git push origin friday-plan/g",
])
def test_hook_denies_plan_push(cmd):
    assert hook.check_deny(cmd)


def test_hook_allows_goal_push():
    assert not hook.check_deny("git push origin friday/core")
