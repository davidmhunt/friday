import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

import friday_status as fs


def _record(tmp_path, monkeypatch, goal, message, t):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    d = tmp_path / "friday" / "waiting"
    d.mkdir(parents=True)
    (d / f"{goal}.json").write_text(json.dumps({"goal": goal, "message": message, "time": t}))


def test_session_carries_the_hook_record_with_age(tmp_path, monkeypatch):
    _record(tmp_path, monkeypatch, "g1", "Claude needs your permission to use Bash", 900)
    st = fs.session_state("friday-g1", 800, None, "idle pane\n> ", now=960)
    assert st["waiting"] is True
    assert st["waiting_line"] == "Claude needs your permission to use Bash"
    assert st["waiting_age"] == 60
    assert fs.check_schema({**fs.empty_snapshot("n", "h", 0), "sessions": [st]}) == []


def test_no_record_falls_back_to_pane_detection(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    st = fs.session_state("friday-g1", 800, None, "Do you want to proceed?\n 1. Yes\n 2. No\n")
    assert st["waiting_age"] is None
    quiet = fs.session_state("friday-g2", 800, None, "working...\n")
    assert quiet["waiting"] is False and quiet["waiting_age"] is None


# --- friday nodes --waiting, with a fake ssh ---

import os
import subprocess

FRIDAY = Path(__file__).resolve().parent.parent / "bin" / "friday"
NODES = '''[node.laptop]
role = "master"
ssh = "me@laptop"
repos = "~/r"
plugin_dir = "~/f"
[node.alfred]
role = "worker"
ssh = "me@alfred"
repos = "~/r"
plugin_dir = "~/f"
'''
SESSION = {"name": "friday-g1", "goal": "g1", "directive": "d-01", "waiting": True,
           "waiting_line": "Claude needs your permission to use Bash", "waiting_age": 125}


def _waiting(tmp_path, per_host):
    """per_host: ssh target -> sessions list, or None for unreachable."""
    (tmp_path / "n.toml").write_text(NODES)
    ssh = tmp_path / "fakessh"
    cases = "\n".join(
        f'  *{h}*) ' + ("exit 255" if v is None else f"echo '{json.dumps({'sessions': v})}'") + " ;;"
        for h, v in per_host.items())
    ssh.write_text(f"#!/bin/bash\ncat >/dev/null\ncase \"$*\" in\n{cases}\nesac\n")
    ssh.chmod(0o755)
    env = dict(os.environ, FRIDAY_NODES=str(tmp_path / "n.toml"), FRIDAY_SSH=str(ssh), HOME=str(tmp_path))
    return subprocess.run([sys.executable, str(FRIDAY), "nodes", "--waiting"], env=env,
                          capture_output=True, text=True, cwd=tmp_path)


def test_nodes_waiting_none_is_0(tmp_path):
    quiet = {**SESSION, "waiting": False}
    r = _waiting(tmp_path, {"laptop": [quiet], "alfred": []})
    assert r.returncode == 0
    assert "g1" not in r.stdout


def test_nodes_waiting_some_is_10_with_a_line(tmp_path):
    r = _waiting(tmp_path, {"laptop": [], "alfred": [SESSION]})
    assert r.returncode == 10
    assert "alfred g1 d-01 2m Claude needs your permission to use Bash" in r.stdout


def test_nodes_waiting_unreachable_is_2(tmp_path):
    r = _waiting(tmp_path, {"laptop": [SESSION], "alfred": None})
    assert r.returncode == 2
    assert "alfred: unreachable" in r.stdout and "laptop g1 d-01" in r.stdout


# --- the hook: record, status shows it, the next tool call clears it ---

HOOK = Path(__file__).resolve().parent.parent / "hooks" / "friday_hook.py"


def _hook(tmp_path, event, payload, dispatched=True):
    env = {k: v for k, v in os.environ.items() if k not in ("FRIDAY_DISPATCHED_FROM", "TMUX")}
    env.update(HOME=str(tmp_path), XDG_STATE_HOME=str(tmp_path / "state"))
    if dispatched:
        env["FRIDAY_DISPATCHED_FROM"] = "laptop"
    return subprocess.run([sys.executable, str(HOOK), event], input=json.dumps(payload), env=env,
                          capture_output=True, text=True, cwd=tmp_path)


def _worktree(tmp_path, branch="friday/g1"):
    wt = tmp_path / "wt"
    wt.mkdir()
    subprocess.run(["git", "init", "-q", "-b", branch], cwd=wt, check=True)
    return wt


def _rec(tmp_path):
    return tmp_path / "state" / "friday" / "waiting" / "g1.json"


def test_hook_writes_the_record_and_status_shows_it(tmp_path, monkeypatch):
    wt = _worktree(tmp_path)
    msg = "Claude needs your permission to use Bash"
    r = _hook(tmp_path, "notification", {"cwd": str(wt), "session_id": "s1", "message": msg,
                                         "notification_type": "permission_prompt"})
    assert r.returncode == 0, r.stderr
    rec = json.loads(_rec(tmp_path).read_text())
    assert rec["goal"] == "g1" and rec["message"] == msg and rec["kind"] == "permission_prompt"
    assert rec["tmux_session"] == "friday-g1" and rec["time"] > 0
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    st = fs.session_state("friday-g1", 800, None, "idle pane\n> ", now=rec["time"] + 30)
    assert st["waiting"] is True and st["waiting_line"] == msg and st["waiting_age"] == 30


def test_the_next_tool_call_clears_it(tmp_path):
    wt = _worktree(tmp_path)
    _hook(tmp_path, "notification", {"cwd": str(wt), "session_id": "s1", "message": "m",
                                     "notification_type": "permission_prompt"})
    assert _rec(tmp_path).exists()
    _hook(tmp_path, "waiting-clear", {"cwd": str(wt), "session_id": "s1", "hook_event_name": "PreToolUse"})
    assert not _rec(tmp_path).exists()


def test_idle_notice_is_not_a_prompt(tmp_path):
    wt = _worktree(tmp_path)
    _hook(tmp_path, "notification", {"cwd": str(wt), "message": "idle", "notification_type": "idle_prompt"})
    assert not _rec(tmp_path).exists()


def test_outside_a_friday_worktree_writes_nothing(tmp_path):
    wt = _worktree(tmp_path)          # a git repo, but no marker and not dispatched
    r = _hook(tmp_path, "notification", {"cwd": str(wt), "message": "m",
                                         "notification_type": "permission_prompt"}, dispatched=False)
    assert r.returncode == 0
    assert not (tmp_path / "state" / "friday" / "waiting").exists()
