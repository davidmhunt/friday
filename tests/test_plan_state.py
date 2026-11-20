"""pa-01 (#31): a plan's publish state (published | not published | stale), the start line, and status."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib"))
import friday_core as fc  # noqa: E402
import friday_status as fs  # noqa: E402

CLI = ROOT / "bin" / "friday"

DIRECTIVE = """# core-01: Make the thing
Status: approved
Goal: core
Node: any
Deliverable: code
Land: goal
Verify: true
Hardware: none

## Goal
Make it.

## Steps
1. Create ok.txt

## Out of scope
- nothing
{allowed}
## Log
"""
GOAL = """# core: The core goal
Status: approved
Base: main
Land: pr

## Goal
Do the core.

## Directives
1. core-01: Make the thing

## Log
"""
LINE = 'Allowed commands are NOT pre-approved ({state}): the user runs "! friday approve --goal core"'


def allowed(*pats):
    return "\n## Allowed commands\n" + "".join(f"- `{p}`\n" for p in pats)


def git(r, *a):
    return subprocess.run(["git", "-C", str(r), *a], check=True, capture_output=True, text=True).stdout.strip()


def make(tmp_path, monkeypatch, section):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    r = tmp_path / "repo"
    r.mkdir()
    git(tmp_path, "init", "-q", "-b", "main", str(r))
    for k, v in (("user.name", "t"), ("user.email", "t@t")):
        git(r, "config", k, v)
    (r / "docs" / "directives").mkdir(parents=True)
    (r / "docs" / "goals").mkdir(parents=True)
    (r / "docs" / "goals" / "core.md").write_text(GOAL)
    (r / "docs" / "directives" / "core-01.md").write_text(DIRECTIVE.format(allowed=section))
    git(r, "add", ".")
    git(r, "commit", "--no-verify", "-qm", "init")
    return r


def publish(r):
    git(r, "update-ref", "refs/remotes/origin/friday-plan/core", "main")


def cli(r, *args):
    return subprocess.run([sys.executable, str(CLI), *args], cwd=r, capture_output=True, text=True)


def test_three_states(tmp_path, monkeypatch):
    r = make(tmp_path, monkeypatch, allowed("friday release *"))
    assert fc.plan_publish_state(r, "core-01") == "not published"
    publish(r)
    assert fc.plan_publish_state(r, "core-01") == "published"
    (r / "docs/directives/core-01.md").write_text(DIRECTIVE.format(allowed=allowed("friday release *", "friday nodes")))
    assert fc.plan_publish_state(r, "core-01") == "stale"


def test_no_allowed_commands_has_no_state(tmp_path, monkeypatch):
    r = make(tmp_path, monkeypatch, "")
    assert fc.plan_publish_state(r, "core-01") is None
    assert fc.plan_publish_state(r, "nope-01") is None


def test_start_prints_the_line_only_when_not_published(tmp_path, monkeypatch):
    r = make(tmp_path, monkeypatch, allowed("friday release *"))
    out = cli(r, "start", "core-01")
    assert out.returncode == 0, out.stderr
    assert LINE.format(state="not published") in out.stdout.splitlines()
    git(r, "checkout", "-q", "main")
    git(r, "checkout", "-q", "--", ".")
    git(r, "branch", "-D", "friday/core")
    publish(r)
    out = cli(r, "start", "core-01")
    assert out.returncode == 0, out.stderr
    assert "NOT pre-approved" not in out.stdout


def test_start_without_allowed_commands_prints_no_line(tmp_path, monkeypatch):
    r = make(tmp_path, monkeypatch, "")
    out = cli(r, "start", "core-01")
    assert out.returncode == 0 and "NOT pre-approved" not in out.stdout


@pytest.mark.parametrize("state", ["not published", "published", "stale"])
def test_status_text_and_json(tmp_path, monkeypatch, state):
    r = make(tmp_path, monkeypatch, allowed("friday release *"))
    if state != "not published":
        publish(r)
    if state == "stale":
        (r / "docs/directives/core-01.md").write_text(DIRECTIVE.format(allowed=allowed("friday nodes")))
        git(r, "commit", "--no-verify", "-qam", "widen")
    assert cli(r, "start", "core-01").returncode == 0
    text = cli(r, "status").stdout
    assert f"plan: {state}" in next(l for l in text.splitlines() if l.startswith("goal core"))
    errors = []
    goal = next(g for g in fs.collect_repo(r, errors)["goals"] if g["id"] == "core")
    assert goal["plan"] == state and not errors


def test_status_omits_plan_without_allowed_commands(tmp_path, monkeypatch):
    r = make(tmp_path, monkeypatch, "")
    assert cli(r, "start", "core-01").returncode == 0
    assert "plan:" not in cli(r, "status").stdout
    goal = next(g for g in fs.collect_repo(r, [])["goals"] if g["id"] == "core")
    assert "plan" not in goal
