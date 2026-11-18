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
    git(clone, "config", "user.name", "t"); git(clone, "config", "user.email", "t@t")
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
    (home / ".local" / "bin" / "friday").symlink_to(FRIDAY)
    fake = home / ".local" / "bin" / "tmux"
    fake.write_text("#!/bin/bash\ncase \"$1\" in capture-pane|has-session) exit 1;; esac\nexit 0\n")
    fake.chmod(0o755)
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


def directives(e, statuses, goal="g1"):
    """Commit a goal file listing d1.. with the given Statuses into the worktree (and a different one in
    the master clone, to prove the worktree's copy is the one read)."""
    wt = e.repos / "proj.friday" / goal
    ids = [f"d{i}" for i in range(1, len(statuses) + 1)]
    (wt / "docs" / "directives").mkdir(parents=True, exist_ok=True)
    body = "\n".join(f"{i}. {d}: title" for i, d in enumerate(ids, 1))
    (wt / "docs" / "goals" / f"{goal}.md").write_text(
        f"# {goal}: g\nStatus: running\n\n## Directives\n{body}\n\n## Log\n")
    for d, st in zip(ids, statuses):
        (wt / "docs" / "directives" / f"{d}.md").write_text(f"# {d}: t\nStatus: {st}\nGoal: {goal}\n\n## Log\n")
    git(wt, "add", ".")
    git(wt, "commit", "-qm", "directives")
    return ids


def session(e, pane, goal="g1"):
    (e.tmp / f"friday-{goal}.pane").write_text(pane)
    tmux = ["#!/bin/bash", 'sub=$1; shift; t=; while [ $# -gt 0 ]; do [ "$1" = -t ] && t=$2; shift; done',
            't=${t#=}; t=${t%:}', f'f="{e.tmp}/${{t}}.pane"', 'if [ "$sub" = capture-pane ]; then [ -f "$f" ] && cat "$f" || exit 1; fi', "exit 0"]
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
    directives(env, ["approved"])
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
    directives(env, ["approved"])
    session(env, "done\n\n❯ \n")
    rc, out, err = resume(env)
    assert rc == 0, err
    assert "exists and is idle" in out and "uncommitted files: none" in out


def test_node_from_latest_record_or_flag(env):
    record(env, node="gone")
    record(env)  # latest wins
    worktree(env)
    directives(env, ["approved"])
    assert resume(env)[0] == 0
    assert resume(env, "--node", "w")[0] == 0
    rc, _, err = resume(env, "--node", "nope")
    assert rc == 18 and "not a master or worker" in err


def test_no_record_and_no_node_refuses(env):
    worktree(env)
    directives(env, ["approved"])
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


def test_remaining_after_blocked_land_lists_only_later(env):
    record(env)
    worktree(env)
    directives(env, ["done", "approved", "approved"])
    rc, out, err = resume(env)
    assert rc == 0, err
    assert "remaining directives" in out
    rem = out.split("remaining directives", 1)[1]
    assert "d2" in rem and "d3" in rem and "d1" not in rem


def test_reads_worktree_goal_file_not_master(env):
    record(env)
    worktree(env)
    directives(env, ["done", "done", "approved"])
    (env.proj / "docs" / "goals").mkdir(parents=True)
    (env.proj / "docs" / "goals" / "g1.md").write_text(
        "# g1: g\nStatus: running\n\n## Directives\n1. d1: t\n2. d2: t\n")
    rc, out, _ = resume(env)
    rem = out.split("remaining directives", 1)[1]
    assert rc == 0 and "d3" in rem and "d1" not in rem and "d2" not in rem


def test_blocked_directive_refuses_without_unblock(env):
    record(env)
    wt = worktree(env)
    directives(env, ["done", "blocked: needs a key", "approved"])
    rc, _, err = resume(env)
    assert rc == 25 and "d2" in err and "blocked: needs a key" in err and "--unblock d2" in err
    assert "blocked: needs a key" in (wt / "docs" / "directives" / "d2.md").read_text()


def test_unblock_resets_status_in_one_commit(env):
    record(env)
    wt = worktree(env)
    directives(env, ["done", "blocked: needs a key", "approved"])
    (wt / "a.txt").write_text("wip")
    rc, out, err = resume(env, "--unblock", "d2")
    assert rc == 0, err
    assert "reset d2 to approved" in out and "d2" in out.split("remaining directives", 1)[1]
    assert "Status: approved" in (wt / "docs" / "directives" / "d2.md").read_text()
    st = subprocess.run(["git", "status", "--porcelain"], cwd=wt, capture_output=True, text=True).stdout
    assert " M a.txt" in st and "d2.md" not in st and (wt / "a.txt").read_text() == "wip"
    assert "d2: unblock" in subprocess.run(["git", "log", "-1", "--format=%s"], cwd=wt, capture_output=True, text=True).stdout
    assert "Status: approved" in (wt / "docs" / "directives" / "d3.md").read_text()


def test_unblock_dry_run_changes_nothing_and_unknown_id_refuses(env):
    record(env)
    wt = worktree(env)
    directives(env, ["blocked: x"])
    rc, out, _ = resume(env, "--unblock", "d1", "--dry-run")
    assert rc == 0 and "would reset d1" in out
    assert "blocked: x" in (wt / "docs" / "directives" / "d1.md").read_text()
    rc, _, err = resume(env, "--unblock", "zz")
    assert rc == 26 and "not a directive" in err


def logging_tmux(e):
    """A tmux that logs every call to tmux.log; capture-pane answers from the pane file."""
    log = e.tmp / "tmux.log"
    script = ["#!/bin/bash", 'echo "$@" >> "%s"' % log,
              'f="%s/friday-g1.pane"' % e.tmp,
              'case "$1" in capture-pane) [ -f "$f" ] && cat "$f" || exit 1;; has-session) [ -f "$f" ] || exit 1;; esac',
              "exit 0"]
    p = e.home / ".local" / "bin" / "tmux"
    p.write_text("\n".join(script) + "\n")
    p.chmod(0o755)
    return log


def records(e):
    p = Path(e.env["XDG_STATE_HOME"]) / "friday" / "dispatches.jsonl"
    return [json.loads(l) for l in p.read_text().splitlines()]


def test_restart_kills_idle_session_launches_remaining_and_records(env):
    record(env, report_to="boss")
    wt = worktree(env)
    directives(env, ["done", "approved", "approved"])
    (env.tmp / "friday-g1.pane").write_text("done\n\n❯ \n")
    log = logging_tmux(env)
    rc, out, err = resume(env)
    assert rc == 0, err
    calls = log.read_text()
    k, nw = calls.find("kill-session -t =friday-g1"), calls.find("new -d -s friday-g1")
    assert 0 <= k < nw
    launch = calls[nw:]
    assert f"-c {wt}" in launch and "d2" in launch and "d3" in launch and "d1" not in launch.split("Run the remaining directives", 1)[1]
    rec = records(env)[-1]
    assert rec["kind"] == "resume" and rec["goal"] == "g1" and rec["node"] == "w"
    assert rec["directives"] == ["d2", "d3"] and rec["worktree"] == str(wt)


def test_restart_without_session_does_not_kill(env):
    record(env, report_to="boss")
    worktree(env)
    directives(env, ["approved"])
    log = logging_tmux(env)
    rc, _, err = resume(env)
    assert rc == 0, err
    calls = log.read_text()
    assert "kill-session" not in calls and "new -d -s friday-g1" in calls


def test_restart_dry_run_prints_launch_only(env):
    record(env, report_to="boss")
    worktree(env)
    directives(env, ["done", "approved"])
    (env.tmp / "friday-g1.pane").write_text("❯ \n")
    log = logging_tmux(env)
    n_before = len(records(env))
    rc, out, err = resume(env, "--dry-run")
    assert rc == 0, err
    assert "kill: tmux kill-session -t =friday-g1" in out and "launch: tmux new -d -s friday-g1" in out
    assert "d2" in out and "remaining directives" in out
    assert "kill-session" not in log.read_text() and "new -d" not in log.read_text()
    assert len(records(env)) == n_before
