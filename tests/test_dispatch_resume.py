"""`friday dispatch --goal <g> --resume` checks. Fake ssh runs the remote script locally under a temp HOME
with a fake tmux. Run: uv run --with pytest pytest -q tests/test_dispatch_resume.py"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FRIDAY = ROOT / "bin" / "friday"
GIT = ["git", "-c", "user.name=t", "-c", "user.email=t@t"]

FAKE_SSH = """#!/bin/sh
exec env HOME="$FAKE_HOME" bash -s
"""


def git(cwd, *a):
    subprocess.run([*GIT, *a], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def env(tmp_path):
    home = tmp_path / "home"
    (home / ".local" / "bin").mkdir(parents=True)
    repos = tmp_path / "repos"
    clone = repos / "proj"
    clone.mkdir(parents=True)
    git(clone, "init", "-q", "-b", "main")
    (clone / "a.txt").write_text("a")
    git(clone, "add", ".")
    git(clone, "commit", "-qm", "init")
    proj = tmp_path / "master"
    proj.mkdir()
    git(proj, "init", "-q", "-b", "main")
    git(proj, "remote", "add", "origin", "git@github.com:me/proj.git")
    ssh = tmp_path / "ssh"
    ssh.write_text(FAKE_SSH)
    ssh.chmod(0o755)
    nodes = tmp_path / "nodes.toml"
    nodes.write_text(f'report_to = "boss"\n[node.w]\nrole = "worker"\nssh = "me@w"\n'
                     f'repos = "{repos}"\nplugin_dir = "~/friday"\n')
    e = {**os.environ, "FRIDAY_SSH": str(ssh), "FRIDAY_NODES": str(nodes), "FAKE_HOME": str(home),
         "XDG_STATE_HOME": str(tmp_path / "state")}
    return type("E", (), {"home": home, "repos": repos, "clone": clone, "proj": proj, "env": e,
                          "tmp": tmp_path})


def record(e, **kw):
    p = Path(e.env["XDG_STATE_HOME"]) / "friday" / "dispatches.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as f:
        f.write(json.dumps({"goal": "g1", "node": "w", "repo": "proj", **kw}) + "\n")


def worktree(e, status="running", goal="g1"):
    wt = e.repos / "proj.friday" / goal
    git(e.clone, "worktree", "add", "-q", "-b", f"friday/{goal}", str(wt))
    (wt / "docs" / "goals").mkdir(parents=True)
    (wt / "docs" / "goals" / f"{goal}.md").write_text(f"# {goal}: g\nStatus: {status}\n")
    git(wt, "add", ".")
    git(wt, "commit", "-qm", "goal")
    return wt


def session(e, pane, goal="g1"):
    (e.tmp / f"friday-{goal}.pane").write_text(pane)
    tmux = ["#!/bin/bash", 'sub=$1; shift; t=; while [ $# -gt 0 ]; do [ "$1" = -t ] && t=$2; shift; done',
            't=${t#=}; t=${t%:}', f'f="{e.tmp}/${{t}}.pane"', '[ -f "$f" ] || exit 1',
            '[ "$sub" = capture-pane ] && cat "$f"', "exit 0"]
    p = e.home / ".local" / "bin" / "tmux"
    p.write_text("\n".join(tmux) + "\n")
    p.chmod(0o755)


def resume(e, *args):
    r = subprocess.run([sys.executable, str(FRIDAY), "dispatch", "--goal", "g1", "--resume", *args],
                       cwd=e.proj, env=e.env, capture_output=True, text=True)
    return r.returncode, r.stdout, r.stderr


def test_resume_ok_reports_uncommitted_and_keeps_them(env):
    record(env)
    wt = worktree(env)
    (wt / "a.txt").write_text("changed")
    (wt / "new.txt").write_text("x")
    rc, out, err = resume(env)
    assert rc == 0, err
    assert "on w" in out and "friday/g1" in out and "friday-g1 is not running" in out
    assert "uncommitted files (kept, not touched): 2" in out
    assert "a.txt" in out and "new.txt" in out
    assert (wt / "a.txt").read_text() == "changed" and (wt / "new.txt").exists()


def test_resume_clean_worktree_and_idle_session(env):
    record(env)
    worktree(env)
    session(env, "done\n\n❯ \n")
    rc, out, err = resume(env)
    assert rc == 0, err
    assert "exists and is idle" in out and "uncommitted files: none" in out


def test_node_from_latest_record_or_flag(env):
    record(env, node="gone")
    record(env)  # latest wins
    worktree(env)
    assert resume(env)[0] == 0
    assert resume(env, "--node", "w")[0] == 0
    rc, _, err = resume(env, "--node", "nope")
    assert rc == 18 and "not a master or worker" in err


def test_no_record_and_no_node_refuses(env):
    worktree(env)
    rc, _, err = resume(env)
    assert rc == 21 and "no dispatch record" in err
    assert resume(env, "--node", "w")[0] == 0


def test_missing_worktree_refuses(env):
    record(env)
    rc, _, err = resume(env)
    assert rc == 22 and "normal dispatch" in err


def test_wrong_branch_refuses(env):
    record(env)
    wt = worktree(env)
    git(wt, "checkout", "-q", "-b", "other")
    rc, _, err = resume(env)
    assert rc == 22 and "not friday/g1" in err


def test_goal_done_refuses(env):
    record(env)
    worktree(env, status="done")
    rc, _, err = resume(env)
    assert rc == 23 and "done" in err


@pytest.mark.parametrize("pane", ["working\nesc to interrupt\n", "Do you want to proceed?\n❯ 1. Yes\n"])
def test_busy_or_waiting_session_refuses(env, pane):
    record(env)
    worktree(env)
    session(env, pane)
    rc, _, err = resume(env)
    assert rc == 24 and "busy or waiting" in err
