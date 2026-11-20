"""Step 3 of status-02: per-node state, persistence, stale/missing, master snapshot, gh PRs.
Run: uv run --with pytest --with pyyaml pytest -q tests/test_dash_state.py"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib"))
import friday_dash as fd  # noqa: E402
import friday_fleet as ff  # noqa: E402
import friday_status as fs  # noqa: E402

REG = """
[node.laptop]
role = "master"
ssh = "me@laptop-ts"
repos = "~/r"
plugin_dir = "~/f"
[node.alfred]
role = "worker"
ssh = "me@alfred-ts"
repos = "~/r"
plugin_dir = "~/f"
[node.ghost]
role = "worker"
ssh = "me@ghost-ts"
repos = "~/r"
plugin_dir = "~/f"
"""


class Clock:
    t = 1000.0

    def __call__(self):
        return self.t


def make(tmp_path, clock, run=subprocess.run, collect=None):
    f = tmp_path / "nodes.toml"
    f.write_text(REG)
    return fd.Dash(ff.load_nodes(f), clock=clock, run=run, state_path=tmp_path / "state", collect=collect)


def snap(node, origin=None):
    s = fs.empty_snapshot(node, node + "-host", 1.0)
    if origin:
        s["repos"].append({"path": "/r", "origin": origin, "branch": "main", "goals": []})
    return s


def test_stale_missing_and_restart(tmp_path):
    clk = Clock()
    d = make(tmp_path, clk)
    d.store("alfred", snap("alfred"))
    st = d.state()["nodes"]
    assert st["alfred"]["status"] == "ok" and st["alfred"]["last_seen"] == 1000.0
    assert st["ghost"]["status"] == "missing" and st["ghost"]["report"] is None
    clk.t += 90
    assert d.state()["nodes"]["alfred"]["status"] == "ok"
    clk.t += 1
    assert d.state()["nodes"]["alfred"]["status"] == "stale"
    saved = tmp_path / "state" / "alfred.json"
    assert json.loads(saved.read_text())["report"]["node"] == "alfred"
    assert not list((tmp_path / "state").glob(".*tmp*"))
    d2 = make(tmp_path, clk)  # restart: last known state, aged by its receive time
    n = d2.state()["nodes"]
    assert n["alfred"]["status"] == "stale" and n["alfred"]["report"]["node"] == "alfred"
    assert n["ghost"]["status"] == "missing"


def test_corrupt_saved_state_is_skipped(tmp_path):
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "alfred.json").write_text("{nope")
    (tmp_path / "state" / "ghost.json").write_text(json.dumps({"received": 1, "report": snap("other")}))
    d = make(tmp_path, Clock())
    assert d.state()["nodes"]["alfred"]["status"] == "missing"
    assert d.state()["nodes"]["ghost"]["status"] == "missing"


def test_master_snapshot_in_process(tmp_path):
    seen = {}

    def collect(registry_path, node_name):
        seen["name"] = node_name
        return snap(node_name)
    d = make(tmp_path, Clock(), collect=collect)
    assert d.refresh_master()
    assert seen["name"] == "laptop"
    assert d.state()["nodes"]["laptop"]["status"] == "ok"
    assert (tmp_path / "state" / "laptop.json").exists()


def fake_run(calls, fail=None):
    def run(argv, **kw):
        calls.append(argv)
        if fail:
            raise fail
        prs = [{"number": 1, "title": "t", "url": "u", "headRefName": "friday/x", "isDraft": False,
                "author": {"login": "a"}, "updatedAt": "z"},
               {"number": 2, "title": "o", "url": "u2", "headRefName": "feature/y", "isDraft": False,
                "author": {"login": "a"}, "updatedAt": "z"}]
        return subprocess.CompletedProcess(argv, 0, json.dumps(prs), "")
    return run


def test_prs_from_gh_and_skip_when_missing(tmp_path):
    calls = []
    d = make(tmp_path, Clock(), run=fake_run(calls))
    d.store("alfred", snap("alfred", "git@github.com:me/proj.git"))
    d.store("laptop", snap("laptop", "https://github.com/me/proj"))
    d.refresh_prs()
    assert len(calls) == 1 and calls[0][:5] == ["gh", "pr", "list", "-R", "me/proj"]
    s = d.state()
    assert [p["number"] for p in s["prs"]] == [1] and s["prs"][0]["repo"] == "me/proj"
    assert s["prs_note"] is None
    d.run = fake_run([], fail=FileNotFoundError("gh"))
    d.refresh_prs()
    s = d.state()
    assert "gh is not installed" in s["prs_note"] and len(s["prs"]) == 1  # old list kept


def test_state_nodes_carry_role(tmp_path):
    d = make(tmp_path, Clock())
    d.reports["stranger"] = snap("stranger")
    d.received["stranger"] = d.clock()
    nodes = d.state()["nodes"]
    assert nodes["laptop"]["role"] == "master"
    assert nodes["alfred"]["role"] == "worker"
    assert nodes["ghost"]["role"] == "worker"  # missing node still has its registry role
    assert nodes["stranger"]["role"] is None  # not in the registry
