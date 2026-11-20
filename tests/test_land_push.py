"""A goal with `Land: push` lands by pushing friday/<goal> only: PUSHED and COMPARE lines, a Log entry,
no gh or glab call. Run: uv run --with pytest --with pyyaml pytest -q tests/test_land_push.py"""
import json
import re
import subprocess
from pathlib import Path

import pytest

from test_friday import cli, done_goal, grepo2, _fake_gh, _git, _heads  # noqa: F401  (fixtures)

SRC = (Path(__file__).resolve().parent.parent / "workflows" / "execute.js").read_text()


@pytest.fixture
def push_goal(done_goal, tmp_path, monkeypatch):
    """done_goal with `Land: push`, a gitlab-style origin URL that a fake ssh serves from the bare repo,
    and fake gh and glab that log any call."""
    repo, origin = done_goal
    _git(repo, "remote", "set-url", "origin", "git@gitlab.example.com:o/r.git")
    ssh = tmp_path / "fakessh"
    ssh.write_text(f"#!/bin/sh\nexec sh -c \"$(printf '%s' \"$2\" | sed \"s#'[^']*'#'{origin}'#\")\"\n")
    ssh.chmod(0o755)
    monkeypatch.setenv("GIT_SSH_COMMAND", str(ssh))
    cfg = repo / ".claude" / "friday.json"
    cfg.write_text(json.dumps({**json.loads(cfg.read_text()), "forge": "gitlab"}))
    g = repo / "docs/goals/core.md"
    g.write_text(g.read_text().replace("Land: pr", "Land: push"))
    _git(repo, "add", "-A")
    _git(repo, "commit", "--no-verify", "-qm", "push goal")
    log = tmp_path / "forge.log"
    for name in ("gh", "glab"):
        f = tmp_path / f"{name}-spy"
        f.write_text(f"#!/bin/sh\necho {name} \"$@\" >> {log}\nexit 0\n")
        f.chmod(0o755)
    monkeypatch.setenv("FRIDAY_GH", str(tmp_path / "gh-spy"))
    monkeypatch.setenv("FRIDAY_GLAB", str(tmp_path / "glab-spy"))
    return repo, origin, log


def test_land_push_pushes_prints_and_logs(push_goal):
    repo, origin, log = push_goal
    r = cli(repo, "land", "--goal", "core")
    assert r.returncode == 0, r.stdout + r.stderr
    lines = r.stdout.strip().splitlines()
    assert "PUSHED: friday/core" in lines
    assert lines[-1] == "COMPARE: https://gitlab.example.com/o/r/-/compare/main...friday/core"
    assert "friday/core" in _heads(origin)
    g = (repo / "docs/goals/core.md").read_text()
    assert "Status: done" in g and "pushed friday/core (no PR)" in g
    assert _git(repo, "status", "--porcelain") == ""
    assert not log.exists()


def test_land_push_without_web_url_prints_no_compare(done_goal, tmp_path, monkeypatch):
    repo, origin = done_goal
    g = repo / "docs/goals/core.md"
    g.write_text(g.read_text().replace("Land: pr", "Land: push"))
    _git(repo, "commit", "--no-verify", "-qam", "push goal")
    fake, log, _ = _fake_gh(tmp_path)
    monkeypatch.setenv("FRIDAY_GH", str(fake))
    r = cli(repo, "land", "--goal", "core")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "PUSHED: friday/core" in r.stdout and "COMPARE" not in r.stdout
    assert not log.exists()


def test_land_push_failing_reverify_stops_before_push(push_goal):
    repo, origin, log = push_goal
    p = repo / "docs/directives/core-02.md"
    p.write_text(p.read_text().replace("Verify: true", "Verify: false"))
    _git(repo, "commit", "--no-verify", "-qam", "break")
    r = cli(repo, "land", "--goal", "core")
    assert r.returncode == 6 and "nothing pushed" in r.stdout
    assert "PUSHED" not in r.stdout and "friday/core" not in _heads(origin)
    assert "Status: approved" in (repo / "docs/goals/core.md").read_text()
    assert not log.exists()


def test_status_shows_pushed(push_goal):
    repo, _, _ = push_goal
    r = cli(repo, "status")
    assert r.returncode == 0, r.stderr
    lines = [l for l in r.stdout.splitlines() if "pushed" in l]
    assert len(lines) == 1 and "core" in lines[0] and "pr " not in lines[0], r.stdout


def test_execute_js_treats_push_like_pr():
    i = SRC.index("const goalCmd")
    block = SRC[i:]
    assert "friday land --goal ${d.goal}" in block
    assert re.search(r"/\^PUSHED: /m", block) and re.search(r"/\^COMPARE: ", block)
    assert "pushedOnly" in block and "compare" in block
    assert "Land: push" in SRC.split("export const meta")[1].split("]")[0]
