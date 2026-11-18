"""Tests for `friday init` (cli-03). Run: uv run --with pytest pytest -q tests/test_init.py"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib"))
import friday_core as fc  # noqa: E402

FRIDAY = ROOT / "bin" / "friday"


@pytest.fixture
def repo(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    return tmp_path


def init(repo):
    r = subprocess.run([sys.executable, str(FRIDAY), "init"], cwd=repo, capture_output=True, text=True)
    return r.returncode, r.stdout, r.stderr


def settings(repo):
    return json.loads((repo / ".claude" / "settings.json").read_text())


def test_creates_from_nothing(repo):
    rc, out, _ = init(repo)
    assert rc == 0 and "added" in out
    assert settings(repo) == {"permissions": {"allow": fc.FRIDAY_ALLOW}}


def test_merges_keeping_keys_rules_and_order(repo):
    p = repo / ".claude" / "settings.json"
    p.parent.mkdir()
    existing = {"model": "opus", "permissions": {"allow": ["Bash(ls)", fc.FRIDAY_ALLOW[0]], "deny": ["Bash(rm *)"]},
                "env": {"A": "1"}}
    p.write_text(json.dumps(existing))
    rc, out, _ = init(repo)
    assert rc == 0
    data = settings(repo)
    assert data["model"] == "opus" and data["env"] == {"A": "1"}
    assert data["permissions"]["deny"] == ["Bash(rm *)"]
    assert data["permissions"]["allow"] == ["Bash(ls)", fc.FRIDAY_ALLOW[0], *fc.FRIDAY_ALLOW[1:]]
    assert fc.FRIDAY_ALLOW[0] not in out.split("added", 1)[1]


def test_idempotent(repo):
    init(repo)
    before = (repo / ".claude" / "settings.json").read_text()
    rc, out, _ = init(repo)
    assert rc == 0 and "nothing to add" in out
    assert (repo / ".claude" / "settings.json").read_text() == before


def test_unparsable_refused_and_untouched(repo):
    p = repo / ".claude" / "settings.json"
    p.parent.mkdir()
    p.write_text("{ not json")
    rc, _, err = init(repo)
    assert rc != 0 and str(p) in err
    assert p.read_text() == "{ not json"


def test_never_touches_local_settings(repo):
    local = repo / ".claude" / "settings.local.json"
    local.parent.mkdir()
    local.write_text('{"x": 1}')
    init(repo)
    assert local.read_text() == '{"x": 1}'


def test_this_repos_settings_equal_friday_allow():
    data = json.loads((ROOT / ".claude" / "settings.json").read_text())
    assert data["permissions"]["allow"] == fc.FRIDAY_ALLOW
