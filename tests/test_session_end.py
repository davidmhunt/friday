"""Tests for `friday session-end`. Run: uv run --with pytest pytest -q tests/test_session_end.py"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FRIDAY = ROOT / "bin" / "friday"

FAKE_TMUX = """#!/bin/sh
echo "tmux $*" >> "$FAKE_DIR/tmux.log"
[ "$1" = display-message ] && echo "$FAKE_SESSION"
exit 0
"""
FAKE_SETSID = """#!/bin/sh
echo "setsid $*" >> "$FAKE_DIR/setsid.log"
"""


@pytest.fixture
def env(tmp_path):
    repo = tmp_path / "repo"
    (repo / "docs" / "goals").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    bindir = tmp_path / "bin"
    bindir.mkdir()
    for name, body in (("tmux", FAKE_TMUX), ("setsid", FAKE_SETSID)):
        f = bindir / name
        f.write_text(body)
        f.chmod(0o755)
    fake = tmp_path / "fake"
    fake.mkdir()
    e = {**os.environ, "PATH": f"{bindir}:{os.environ['PATH']}", "FAKE_DIR": str(fake),
         "FAKE_SESSION": "friday-g1", "FRIDAY_DISPATCHED_FROM": "laptop"}
    return repo, fake, e


def goal(repo, status="done", gid="g1"):
    (repo / "docs" / "goals" / f"{gid}.md").write_text(f"# {gid}: A goal\nStatus: {status}\n\n## Goal\nx\n")


def run(repo, e, gid="g1"):
    return subprocess.run([sys.executable, str(FRIDAY), "session-end", "--goal", gid],
                          cwd=repo, env=e, capture_output=True, text=True)


def scheduled(fake):
    f = fake / "setsid.log"
    return f.read_text() if f.exists() else ""


def test_acts_when_all_three_conditions_hold(env):
    repo, fake, e = env
    goal(repo)
    r = run(repo, e)
    assert r.returncode == 0, r.stderr
    log = scheduled(fake)
    assert "sleep 10; tmux kill-session -t '=friday-g1'" in log
    assert log.startswith("setsid sh -c ")
    assert "kill-session -t '=friday-g1'" in r.stdout
    # the fake tmux was only asked for the session name; nothing was killed directly
    assert "kill-session" not in (fake / "tmux.log").read_text()


def test_refuses_when_not_dispatched(env):
    repo, fake, e = env
    goal(repo)
    del e["FRIDAY_DISPATCHED_FROM"]
    r = run(repo, e)
    assert r.returncode != 0
    assert "not a dispatched session" in r.stderr
    assert scheduled(fake) == ""


def test_refuses_in_a_different_tmux_session(env):
    repo, fake, e = env
    goal(repo)
    e["FAKE_SESSION"] = "friday-other"
    r = run(repo, e)
    assert r.returncode != 0
    assert "friday-other" in r.stderr
    assert scheduled(fake) == ""


@pytest.mark.parametrize("status", ["approved", "blocked", "active"])
def test_refuses_when_goal_not_done(env, status):
    repo, fake, e = env
    goal(repo, status)
    r = run(repo, e)
    assert r.returncode != 0
    assert "not done" in r.stderr
    assert scheduled(fake) == ""


def test_refuses_when_goal_file_missing(env):
    repo, fake, e = env
    r = run(repo, e)
    assert r.returncode != 0
    assert scheduled(fake) == ""


def test_never_targets_another_session(env):
    repo, fake, e = env
    # goal g2 is done, but we sit in friday-g1: must refuse, never schedule a kill of any session
    goal(repo, "done", "g2")
    r = run(repo, e, "g2")
    assert r.returncode != 0
    assert scheduled(fake) == ""
    # when it does act, the only target is =friday-<g>
    goal(repo, "done", "g2")
    e["FAKE_SESSION"] = "friday-g2"
    r = run(repo, e, "g2")
    assert r.returncode == 0, r.stderr
    log = scheduled(fake)
    assert log.count("kill-session") == 1
    assert "-t '=friday-g2'" in log and "friday-g1" not in log


def test_rejects_malformed_goal_id(env):
    repo, fake, e = env
    r = run(repo, e, "g1; rm -rf x")
    assert r.returncode != 0
    assert scheduled(fake) == ""
