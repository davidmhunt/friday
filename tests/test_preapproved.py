"""gate-03: commands pre-approved in `## Allowed commands` run without a prompt during that directive."""
import json
import os
import subprocess
import sys

import pytest

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib"))
import friday_core as fc  # noqa: E402

HOOK = ROOT / "hooks" / "friday_hook.py"

DIRECTIVE = """# core-01: Make the thing
Status: approved
Goal: core
Node: any
Deliverable: code
Land: pr
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
# The last entry is written straight into a directive the hook reads from Base (check would reject
# it), to prove the hook's deny list still wins over a pattern.
ALLOWED = ["friday dispatch *", "friday nodes --clean", "friday release radar", "./flash_radar *",
           "git push --force *"]


def allowed_section(pats):
    return "\n## Allowed commands\n" + "".join(f"- `{p}`\n" for p in pats)


def git(r, *a):
    subprocess.run(["git", "-C", str(r), *a], check=True, capture_output=True)


def make_repo(tmp_path, monkeypatch, base_allowed, branch_allowed=None):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    r = tmp_path / "repo"
    r.mkdir()
    git(tmp_path, "init", "-q", "-b", "main", str(r))
    for k, v in (("user.name", "t"), ("user.email", "t@t")):
        git(r, "config", k, v)
    (r / ".claude").mkdir()
    (r / ".claude" / "friday.json").write_text(json.dumps({"hardware": {"radar": [r"\bflash_radar\b"]}}))
    (r / "docs" / "directives").mkdir(parents=True)
    (r / "docs" / "goals").mkdir(parents=True)
    (r / "docs" / "goals" / "core.md").write_text(GOAL)
    dpath = r / "docs" / "directives" / "core-01.md"
    dpath.write_text(DIRECTIVE.format(allowed=allowed_section(base_allowed) if base_allowed else ""))
    git(r, "add", ".")
    git(r, "commit", "--no-verify", "-qm", "init")
    git(r, "update-ref", "refs/remotes/origin/main", "main")   # the pushed Base the hook trusts
    git(r, "checkout", "-qb", "friday/core")
    if branch_allowed is not None:
        dpath.write_text(DIRECTIVE.format(allowed=allowed_section(branch_allowed)))
        git(r, "commit", "--no-verify", "-qam", "widen")
    return r


@pytest.fixture
def repo(tmp_path, monkeypatch):
    r = make_repo(tmp_path, monkeypatch, ALLOWED)
    fc.write_marker(r, {"id": "core-01", "goal_base": "main"})
    return r


def pre(repo, cmd, session="s1"):
    out = subprocess.run([sys.executable, str(HOOK), "pretool"], capture_output=True, text=True, env=os.environ,
                         input=json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd},
                                           "cwd": str(repo), "session_id": session}))
    assert out.returncode == 0, out.stderr
    if not out.stdout.strip():
        return None, ""
    d = json.loads(out.stdout)["hookSpecificOutput"]
    return d["permissionDecision"], d["permissionDecisionReason"]


def test_matching_command_allowed(repo):
    d, why = pre(repo, "friday dispatch core-01 --node robot")
    assert d == "allow" and "pre-approved in core-01 (on main)" in why
    assert pre(repo, "friday nodes --clean")[0] == "allow"
    assert pre(repo, "friday nodes --list")[0] is None


def test_pattern_only_in_goal_branch_copy_gives_no_decision(tmp_path, monkeypatch):
    r = make_repo(tmp_path, monkeypatch, [], branch_allowed=["friday release *"])
    fc.write_marker(r, {"id": "core-01", "goal_base": "main"})
    assert "friday release *" in (r / "docs" / "directives" / "core-01.md").read_text()
    assert pre(r, "friday release radar")[0] is None


def test_base_without_a_copy_gives_no_decision(tmp_path, monkeypatch):
    r = make_repo(tmp_path, monkeypatch, ALLOWED)
    fc.write_marker(r, {"id": "core-09", "goal_base": "main"})
    assert pre(r, "friday nodes --clean")[0] is None


@pytest.mark.parametrize("cmd", [
    "friday nodes --clean && echo hi", "friday nodes --clean; echo hi", "friday nodes --clean | cat",
    "friday nodes --clean & echo hi", "friday dispatch x $(echo y)", "friday dispatch x `id`",
    "friday dispatch x\necho hi", "echo hi && friday nodes --clean",
])
def test_chained_command_not_allowed(repo, cmd):
    assert pre(repo, cmd)[0] != "allow"


def test_deny_list_beats_a_pattern(repo):
    assert pre(repo, "git push --force origin x")[0] == "deny"


def test_friday_accept_never_allowed(tmp_path, monkeypatch):
    r = make_repo(tmp_path, monkeypatch, ["friday *"])
    fc.write_marker(r, {"id": "core-01", "goal_base": "main"})
    assert pre(r, "friday status")[0] == "allow"
    assert pre(r, "friday accept core-01")[0] == "deny"


def test_no_marker_gives_no_decision(repo):
    fc.marker_path(repo).unlink()
    assert pre(repo, "friday nodes --clean")[0] is None


@pytest.mark.parametrize("pat,frag", [
    ("*", "matches everything"), ("friday a && friday b", "&&"), ("friday a; ls", ";"),
    ("friday a | cat", "|"), ("echo $(id)", "$("), ("friday accept core-01", "friday accept"),
    ("sudo ls", "deny list"), ("git push --force *", "deny list"),
])
def test_check_errors(pat, frag):
    issues = fc.validate_directive("core-01", DIRECTIVE.format(allowed=allowed_section([pat])))
    errs = [i.message for i in issues if i.level == "error"]
    assert any(frag in m for m in errs), errs


def test_check_error_without_backticked_pattern():
    text = DIRECTIVE.format(allowed="\n## Allowed commands\n- friday nodes --clean\n")
    errs = [i.message for i in fc.validate_directive("core-01", text) if i.level == "error"]
    assert any("exactly one backticked pattern" in m for m in errs)


def test_check_clean_and_parse():
    text = DIRECTIVE.format(allowed=allowed_section(["friday dispatch *", "friday nodes --clean"]))
    assert not [i for i in fc.validate_directive("core-01", text) if i.level == "error"]
    assert fc.parse_directive_full(text)["allowed"] == ["friday dispatch *", "friday nodes --clean"]


def test_hardware_pre_approved_allows_and_takes_the_lease(repo):
    assert fc.lease_holder("radar") is None
    d, why = pre(repo, "./flash_radar --go")
    assert d == "allow" and "pre-approved" in why and "Lease taken" in why
    assert fc.lease_holder("radar")["session"] == "s1"


def test_hardware_lease_held_elsewhere_denies(repo):
    fc.take_lease("radar", "other", "x")
    d, why = pre(repo, "./flash_radar --go", session="s1")
    assert d == "deny" and "held by another session" in why


def test_editing_goal_base_header_cannot_widen(tmp_path, monkeypatch):
    r = make_repo(tmp_path, monkeypatch, [], branch_allowed=["friday release *"])
    fc.write_marker(r, {"id": "core-01", "goal_base": "main"})
    g = r / "docs" / "goals" / "core.md"
    g.write_text(g.read_text().replace("Base: main", "Base: friday/core"))
    assert pre(r, "friday release radar")[0] is None


def test_marker_without_goal_base_gives_no_decision(repo):
    fc.write_marker(repo, {"id": "core-01"})
    assert pre(repo, "friday nodes --clean")[0] is None


BIN = ROOT / "bin" / "friday"


def start(r):
    out = subprocess.run([sys.executable, str(BIN), "start", "core-01"], cwd=r, capture_output=True, text=True,
                         env=os.environ)
    assert out.returncode == 0, out.stdout + out.stderr
    return out


def edit_goal_base(r, new):
    g = r / "docs" / "goals" / "core.md"
    g.write_text(g.read_text().replace("Base: main", f"Base: {new}"))
    git(r, "commit", "--no-verify", "-qam", "edit base")


@pytest.mark.parametrize("new", ["friday/core", "friday/core-01", "friday/other"])
def test_start_with_edited_base_on_a_friday_branch_gives_no_decision(tmp_path, monkeypatch, new):
    r = make_repo(tmp_path, monkeypatch, [], branch_allowed=["friday release *"])
    if new != "friday/core":
        git(r, "branch", new, "main")                 # exists, so start accepts the edited Base
    edit_goal_base(r, new)
    start(r)
    assert fc.read_marker(r)["goal_base"] == new
    assert pre(r, "friday release radar")[0] is None


def test_start_with_edited_base_on_local_only_branch_gives_no_decision(tmp_path, monkeypatch):
    r = make_repo(tmp_path, monkeypatch, [], branch_allowed=["friday release *"])
    git(r, "branch", "wip")                           # local only, no origin/wip
    edit_goal_base(r, "wip")
    git(r, "checkout", "-q", "wip")
    git(r, "merge", "--no-verify", "-q", "friday/core")   # wip's goal file names wip and lists the pattern
    git(r, "checkout", "-q", "friday/core")
    start(r)
    assert fc.read_marker(r)["goal_base"] == "wip"
    assert "friday release *" in subprocess.run(["git", "-C", str(r), "show", "wip:docs/directives/core-01.md"],
                                                capture_output=True, text=True).stdout
    assert pre(r, "friday release radar")[0] is None


def test_pattern_on_local_base_but_not_pushed_gives_no_decision(tmp_path, monkeypatch):
    r = make_repo(tmp_path, monkeypatch, [])
    git(r, "checkout", "-q", "main")
    (r / "docs" / "directives" / "core-01.md").write_text(DIRECTIVE.format(allowed=allowed_section(["friday release *"])))
    git(r, "commit", "--no-verify", "-qam", "local only")
    git(r, "checkout", "-q", "friday/core")
    start(r)
    assert pre(r, "friday release radar")[0] is None


@pytest.mark.parametrize("cmd", [
    "git push origin main", "git push origin friday/other", "git push origin HEAD:friday/other",
    "git push origin friday/core", "git push origin friday/core:main", "git push --all",
    "cd . && git push origin wip", "git -C . push origin wip", "git push origin friday/core-01 wip",
])
def test_push_guard_denies(repo, cmd):
    git(repo, "checkout", "-qb", "friday/core-01")
    d, why = pre(repo, cmd)
    assert d == "deny", (cmd, why)


@pytest.mark.parametrize("cmd", [
    "git push origin friday/core-01", "git push -u origin friday/core-01", "git push origin HEAD",
    "git push origin HEAD:friday/core-01", "git push origin friday/core-01:friday/core-01", "git push origin",
    "git -C . push origin friday/core-01", "cd . && git push origin friday/core-01", "git push",
])
def test_push_guard_allows_the_directive_branch(repo, cmd):
    git(repo, "checkout", "-qb", "friday/core-01")
    git(repo, "update-ref", "refs/remotes/origin/friday/core-01", "HEAD")
    git(repo, "config", "branch.friday/core-01.remote", "origin")
    git(repo, "config", "branch.friday/core-01.merge", "refs/heads/friday/core-01")
    assert pre(repo, cmd)[0] != "deny"


def test_push_guard_judges_a_bare_push_by_its_upstream(repo):
    git(repo, "checkout", "-qb", "friday/core-01")
    git(repo, "config", "remote.origin.url", ".")
    git(repo, "config", "remote.origin.fetch", "+refs/heads/*:refs/remotes/origin/*")
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    git(repo, "config", "branch.friday/core-01.remote", "origin")
    git(repo, "config", "branch.friday/core-01.merge", "refs/heads/main")
    assert pre(repo, "git push")[0] == "deny"


def test_push_guard_allows_goal_branch_for_land_goal(tmp_path, monkeypatch):
    r = make_repo(tmp_path, monkeypatch, ALLOWED)
    fc.write_marker(r, {"id": "core-01", "goal_base": "main"})
    p = r / "docs" / "directives" / "core-01.md"
    p.write_text(p.read_text().replace("Land: pr", "Land: goal"))
    assert pre(r, "git push origin friday/core")[0] != "deny"
    assert pre(r, "git push origin friday/core-01")[0] == "deny"


def test_push_without_a_directive_is_not_guarded(repo):
    fc.marker_path(repo).unlink()
    assert pre(repo, "git push origin wip")[0] is None
