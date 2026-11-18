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
