"""Session approval of a hardware resource. Run: uv run --with pytest pytest -q tests/test_hardware_session.py"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / "hooks" / "friday_hook.py"
sys.path.insert(0, str(ROOT / "lib"))


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    r = tmp_path / "repo"
    (r / ".claude").mkdir(parents=True)
    (r / ".claude" / "friday.json").write_text(json.dumps(
        {"hardware": {"radar": [r"\bflash\b"], "gpu": ["train"]},
         "hardware_approval": {"radar": "session"}}))
    subprocess.run(["git", "init", "-q", "-b", "main", str(r)], check=True)
    return r


def run(event, repo, cmd, session):
    p = {"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": str(repo), "session_id": session}
    out = subprocess.run([sys.executable, str(HOOK), event], input=json.dumps(p), capture_output=True,
                         text=True, env=os.environ)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)["hookSpecificOutput"] if out.stdout.strip() else None


def test_session_resource_asks_then_allows_after_posttool(repo):
    assert run("pretool", repo, "flash it", "s1")["permissionDecision"] == "ask"
    assert run("pretool", repo, "flash it", "s1")["permissionDecision"] == "ask"   # not yet run
    run("posttool", repo, "flash it", "s1")
    d = run("pretool", repo, "flash again", "s1")
    assert d["permissionDecision"] == "allow" and d["permissionDecisionReason"] == "radar approved for this session"
    assert run("pretool", repo, "flash again", "s1")["permissionDecision"] == "allow"   # TTL refresh keeps it


def test_command_resource_never_approved(repo):
    run("pretool", repo, "train x", "s1")
    run("posttool", repo, "train x", "s1")
    assert run("pretool", repo, "train y", "s1")["permissionDecision"] == "ask"


def test_other_session_denied_and_cannot_approve(repo):
    run("pretool", repo, "flash", "s1")
    run("posttool", repo, "flash", "s2")        # not the holder: no approval recorded
    assert run("pretool", repo, "flash", "s2")["permissionDecision"] == "deny"
    run("posttool", repo, "flash", "s1")
    assert run("pretool", repo, "flash", "s2")["permissionDecision"] == "deny"


def test_deny_list_still_wins(repo):
    run("pretool", repo, "flash", "s1")
    run("posttool", repo, "flash", "s1")
    d = run("pretool", repo, "sudo flash", "s1")
    assert d["permissionDecision"] == "deny"


def test_release_ends_approval(repo):
    import friday_core as fc
    run("pretool", repo, "flash", "s1")
    run("posttool", repo, "flash", "s1")
    fc.release_leases(resource="radar")
    assert run("pretool", repo, "flash", "s1")["permissionDecision"] == "ask"


def test_default_resource_asks_every_time_with_new_wording(repo):
    for _ in range(2):
        run("pretool", repo, "train x", "s1")
        run("posttool", repo, "train x", "s1")
        d = run("pretool", repo, "train x", "s1")
        assert d["permissionDecision"] == "ask"
        r = d["permissionDecisionReason"]
        assert "held for this session" in r and "covers this command only" in r
        assert "rest of the session" not in r


def test_session_resource_wording_offers_session_approval(repo):
    r = run("pretool", repo, "flash", "s1")["permissionDecisionReason"]
    assert "covers this command only" in r and "rest of the session" in r


def test_bad_hardware_approval_fails_friday_check(repo):
    (repo / ".claude" / "friday.json").write_text(json.dumps(
        {"hardware": {"radar": ["flash"]}, "hardware_approval": {"radar": "always"}}))
    out = subprocess.run([sys.executable, str(ROOT / "bin" / "friday"), "check", "--all"], cwd=str(repo),
                         capture_output=True, text=True)
    assert out.returncode != 0
    assert "hardware_approval" in out.stdout + out.stderr
