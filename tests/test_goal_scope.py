"""Goal scope (scope-01): the plan skill's capability rule, per-goal PR state in `friday status --json`,
and `land --goal` updating an open PR. Run: uv run --with pytest --with pyyaml pytest -q tests/test_goal_scope.py"""
import json
from pathlib import Path

import pytest

from test_friday import cli, done_goal, grepo2, _fake_gh, _git  # noqa: F401  (fixtures)
from test_status_json import snap, tree  # noqa: F401  (fixtures)

ROOT = Path(__file__).resolve().parent.parent


def test_plan_skill_states_capability_rule():
    t = (ROOT / "skills/plan/SKILL.md").read_text()
    low = t.lower()
    assert "one to three" not in low and "one planning run" not in low
    assert "open goal" in low and "extend" in low and "friday status --json" in t
    assert "amendment" in low


def _gh_listing(t, payload):
    """Fake gh whose `pr list` prints `payload` (a list, JSON-encoded)."""
    f = t.tmp / "prs.json"
    f.write_text(json.dumps(payload))
    gh = t.tmp / "gh-fake"
    gh.write_text(f'#!/bin/sh\nPATH=/usr/bin:/bin\n[ "$1 $2" = "pr list" ] && cat {f}\n')
    gh.chmod(0o755)
    return gh


def _alpha_core(t):
    repos = {r["path"]: r for r in snap(t)["repos"]}
    goal = next(g for g in repos[str(t.repos / "alpha")]["goals"] if g["id"] == "core")
    return goal


@pytest.mark.parametrize("payload,state,url", [
    ([], "none", None),
    ([{"state": "CLOSED", "url": "https://x/pull/1", "number": 1}], "none", None),
    ([{"state": "OPEN", "url": "https://x/pull/2", "number": 2}], "open", "https://x/pull/2"),
    ([{"state": "MERGED", "url": "https://x/pull/3", "number": 3}], "merged", "https://x/pull/3"),
])
def test_status_reports_pr_per_goal(tree, monkeypatch, payload, state, url):
    monkeypatch.setenv("FRIDAY_GH", str(_gh_listing(tree, payload)))
    g = _alpha_core(tree)
    assert g["pr"] == state and g["pr_url"] == url


def test_status_omits_pr_without_gh(tree, monkeypatch):
    monkeypatch.delenv("FRIDAY_GH", raising=False)  # PATH holds only git
    g = _alpha_core(tree)
    assert "pr" not in g and "pr_url" not in g


def test_land_goal_with_open_pr_does_not_open_second(done_goal, tmp_path, monkeypatch):
    repo, _ = done_goal
    fake, log, _ = _fake_gh(tmp_path, view_url="https://github.com/o/r/pull/9")
    monkeypatch.setenv("FRIDAY_GH", str(fake))
    r = cli(repo, "land", "--goal", "core")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "PR already open" in r.stdout
    assert r.stdout.strip().splitlines()[-1] == "PR: https://github.com/o/r/pull/9"
    calls = log.read_text()
    assert "pr edit friday/core" in calls and "pr create" not in calls
