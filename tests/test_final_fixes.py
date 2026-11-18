"""Lifecycle fixes from the v1-final audit (fix-01)."""
import json
import os
import subprocess
import sys

from test_friday import CLI, HOOK, DIRECTIVE, repo, cli  # noqa: F401


def _set(repo, *pairs):
    p = repo / "docs" / "directives" / "core-01.md"
    t = DIRECTIVE
    for a, b in pairs:
        t = t.replace(a, b)
    p.write_text(t)
    return p


def test_verify_none_rejected_for_non_external(repo):
    _set(repo, ("Verify: test -f ok.txt", "Verify: none"))
    r = cli(repo, "check", "core-01")
    assert r.returncode != 0
    assert "only for Deliverable external" in r.stdout + r.stderr


EXT = [("Deliverable: code", "Deliverable: external"), ("Verify: test -f ok.txt", "Verify: none"),
       ("Land: pr", "Land: none"), ("\n## Log\n", "\n## Acceptance\n- done\n\n## Log\n")]


def test_verify_none_accepted_for_external(repo):
    _set(repo, *EXT)
    assert cli(repo, "check", "core-01").returncode == 0


def test_verify_none_skipped_by_verify_command(repo):
    _set(repo, *EXT)
    r = cli(repo, "verify", "core-01")
    assert r.returncode == 0 and "Verify none, not run" in r.stdout


def test_verify_none_skipped_by_stop_gate(repo):
    subprocess.run(["git", "-C", str(repo), "checkout", "-qb", "friday/core"], check=True)
    _set(repo, *EXT)
    subprocess.run(["git", "-C", str(repo), "commit", "-qam", "ext"], check=True)
    r = cli(repo, "start", "core-01")
    assert r.returncode == 0, r.stderr
    out = subprocess.run([sys.executable, str(HOOK), "stop"], input=json.dumps({"cwd": str(repo)}),
                         capture_output=True, text=True, env={**os.environ})
    assert out.returncode == 0
    assert "block" not in out.stdout and "none, not run" in out.stdout


def test_empty_hardware_is_error(repo):
    _set(repo, ("Hardware: none", "Hardware:"))
    r = cli(repo, "check", "core-01")
    assert r.returncode != 0
    assert "Hardware must not be empty" in r.stdout + r.stderr


def _pre(repo, cmd):
    out = subprocess.run([sys.executable, str(HOOK), "pretool"], capture_output=True, text=True,
                         input=json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd},
                                           "cwd": str(repo), "session_id": "s"}), env={**os.environ})
    return out.stdout


def test_commit_guard_protects_goal_base(repo):
    g = repo / "docs" / "goals" / "core.md"
    g.write_text(g.read_text().replace("Base: main", "Base: develop"))
    git = lambda *a: subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True)
    git("commit", "-qam", "base develop")
    assert cli(repo, "start", "core-01").returncode == 0
    git("checkout", "-qb", "develop")
    out = _pre(repo, "git commit -m x -m 'Directive: core-01'")
    assert "deny" in out and "friday/core" in out and "develop" in out
    git("checkout", "-q", "friday/core-01")
    assert "deny" not in _pre(repo, "git commit -m x -m 'Directive: core-01'")


def _git(repo, *a):
    return subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True, text=True).stdout




def test_finish_blocked_blocks_goal_and_unblock_resets_both(repo):
    base = cli(repo, "start", "core-01").stdout.split("base ")[1].split()[0]
    r = cli(repo, "finish", "core-01", "--blocked", "needs a key", "--base", base)
    assert r.returncode == 0, r.stderr
    assert "Status: blocked: needs a key" in (repo / "docs/directives/core-01.md").read_text()
    assert "Status: blocked: core-01" in (repo / "docs/goals/core.md").read_text()
    n = _git(repo, "rev-list", "--count", "HEAD").strip()
    (repo / "wip.txt").write_text("x")
    _git(repo, "add", "wip.txt")
    r = cli(repo, "unblock", "core-01")
    assert r.returncode == 0, r.stderr
    assert "Status: approved" in (repo / "docs/directives/core-01.md").read_text()
    assert "Unblocked: was blocked: needs a key" in (repo / "docs/directives/core-01.md").read_text()
    assert "Status: running" in (repo / "docs/goals/core.md").read_text()
    assert int(_git(repo, "rev-list", "--count", "HEAD")) == int(n) + 1
    assert "Directive: core-01" in _git(repo, "log", "-1", "--format=%B")
    assert "wip.txt" not in _git(repo, "show", "--name-only", "--format=", "HEAD")
    assert cli(repo, "check").returncode == 0


def test_unblock_refuses_when_not_blocked_or_off_goal_branch(repo):
    r = cli(repo, "unblock", "core-01")
    assert r.returncode != 0 and "not blocked" in r.stderr
    _git(repo, "checkout", "-q", "main")
    p = repo / "docs/directives/core-01.md"
    p.write_text(p.read_text().replace("Status: approved", "Status: blocked: x"))
    r = cli(repo, "unblock", "core-01")
    assert r.returncode != 0 and "unblock runs on branch" in r.stderr


def _goal_branch(repo, directive_status, verify):
    _git(repo, "checkout", "-q", "main")
    g = repo / "docs/goals/core.md"
    g.write_text(g.read_text().replace("Land: pr", "Land: none"))
    p = repo / "docs/directives/core-01.md"
    p.write_text(p.read_text().replace("Status: approved", f"Status: {directive_status}")
                 .replace("Verify: test -f ok.txt", f"Verify: {verify}"))
    _git(repo, "commit", "-qam", "setup")
    _git(repo, "checkout", "-qb", "friday/core")


def test_land_goal_refuses_unfinished_directive_whatever_its_land(repo):
    _goal_branch(repo, "approved", "true")
    r = cli(repo, "land", "--goal", "core")
    assert r.returncode == 7 and "core-01" in r.stderr
    assert "Status: approved" in (repo / "docs/goals/core.md").read_text()


def test_land_goal_reverifies_every_directive(repo):
    _goal_branch(repo, "done", "false")
    r = cli(repo, "land", "--goal", "core")
    assert r.returncode == 6 and "core-01" in r.stdout and "nothing pushed" in r.stdout
    assert "Status: approved" in (repo / "docs/goals/core.md").read_text()
