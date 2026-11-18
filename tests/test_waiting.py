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
