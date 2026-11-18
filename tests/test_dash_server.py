"""status-02 step 6: friday dash end to end with a fake `tailscale` and `gh` on PATH.
Run: uv run --with pytest pytest -q tests/test_dash_server.py"""
import io
import json
import os
import stat
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib"))
import friday_dash as fd  # noqa: E402
import friday_fleet as ff  # noqa: E402
import friday_status as fs  # noqa: E402

REG = """
[dash]
port = 8787
[node.laptop]
role = "master"
ssh = "me@127.0.0.1"
tailnet = "laptop-ts"
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

PEERS = {"100.64.0.2": "alfred-ts.tail1234.ts.net.", "100.64.0.9": "stranger.tail1234.ts.net."}


class Clock:
    t = 5000.0

    def __call__(self):
        return self.t


@pytest.fixture
def env(tmp_path, monkeypatch):
    """A PATH with a fake tailscale (ip -4, whois --json from peers.json) and a fake gh."""
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    (tmp_path / "peers.json").write_text(json.dumps(PEERS))
    (tmp_path / "prs.json").write_text(json.dumps([
        {"number": 7, "title": "t", "url": "u", "headRefName": "friday/x", "isDraft": False},
        {"number": 8, "title": "other", "url": "u2", "headRefName": "feature/y", "isDraft": False}]))
    ts = bin_ / "tailscale"
    ts.write_text(f"""#!{sys.executable}
import json, sys
a = sys.argv[1:]
if a == ["ip", "-4"]:
    print("100.64.0.1")
elif a[:2] == ["whois", "--json"]:
    n = json.load(open({str(tmp_path / 'peers.json')!r})).get(a[2])
    if n is None:
        sys.exit(1)
    print(json.dumps({{"Node": {{"Name": n}}}}))
else:
    sys.exit(2)
""")
    gh = bin_ / "gh"
    gh.write_text(f"#!/bin/sh\ncat {tmp_path / 'prs.json'}\n")
    for f in (ts, gh):
        f.chmod(f.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", f"{bin_}{os.pathsep}{os.environ['PATH']}")
    (tmp_path / "nodes.toml").write_text(REG)
    return tmp_path


def make(env, clock=None, collect=None):
    return fd.Dash(ff.load_nodes(env / "nodes.toml"), clock=clock or Clock(), state_path=env / "state",
                   collect=collect)


def snap(node, origin=None):
    s = fs.empty_snapshot(node, node + "-host", 1.0)
    if origin:
        s["repos"].append({"path": "/r", "origin": origin, "branch": "main", "goals": []})
    return s


def post(d, peer, body):
    raw = body if isinstance(body, bytes) else json.dumps(body).encode()
    return d.report(peer, {"Content-Length": str(len(raw))}, io.BytesIO(raw))[0]


def test_tailscale_ip_and_whois_via_path(env):
    assert fd.tailnet_ipv4() == "100.64.0.1"
    assert make(env).whois_names("100.64.0.2") == {"alfred-ts.tail1234.ts.net", "alfred-ts"}


def test_accepted_report_from_registry_node(env):
    d = make(env)
    assert post(d, "100.64.0.2", snap("alfred")) == 200
    assert d.state()["nodes"]["alfred"]["status"] == "ok"


def test_rejections(env, capsys):
    d = make(env)
    assert post(d, "100.64.0.9", snap("alfred")) == 403   # device not in the registry
    assert post(d, "100.64.0.77", snap("alfred")) == 403  # whois does not know it
    assert post(d, "192.168.1.5", snap("alfred")) == 403  # not a tailnet peer
    assert post(d, "100.64.0.2", snap("ghost")) == 403    # name / node mismatch
    assert post(d, "100.64.0.2", b"x" * (fd.MAX_BODY + 1)) == 400  # oversize
    assert post(d, "100.64.0.2", b"{not json") == 400
    assert post(d, "100.64.0.2", {"schema": 99, "node": "alfred"}) == 400
    assert post(d, "127.0.0.1", snap("alfred")) == 403    # localhost is the master only
    assert post(d, "127.0.0.1", snap("laptop")) == 200
    nodes = d.state()["nodes"]
    assert nodes["alfred"]["status"] == "missing" and nodes["ghost"]["status"] == "missing"
    assert "refused report" in capsys.readouterr().err


def test_refuses_to_bind_everything():
    for bad in ("0.0.0.0", "::", "192.168.1.5", "example.com"):
        with pytest.raises(fd.DashError):
            fd.resolve_binds([bad], "100.64.0.1")
    assert fd.resolve_binds(None, "100.64.0.1") == ["127.0.0.1", "100.64.0.1"]
    with pytest.raises(fd.DashError):
        fd.DashServer(("0.0.0.0", 0), None)


def test_stale_missing_and_restart(env):
    clk = Clock()
    d = make(env, clk)
    d.store("alfred", snap("alfred"))
    nodes = d.state()["nodes"]
    assert nodes["alfred"]["status"] == "ok" and nodes["ghost"]["status"] == "missing"
    clk.t += 91
    assert d.state()["nodes"]["alfred"]["status"] == "stale"
    n = make(env, clk).state()["nodes"]  # restart
    assert n["alfred"]["status"] == "stale" and n["alfred"]["report"]["node"] == "alfred"
    assert n["ghost"]["status"] == "missing"


def test_state_merges_master_snapshot_and_prs(env):
    d = make(env, collect=lambda registry_path, node_name: snap(node_name, "git@github.com:me/proj.git"))
    assert d.refresh_master()
    d.refresh_prs()  # real subprocess, fake gh on PATH
    st = d.state()
    assert st["nodes"]["laptop"]["status"] == "ok"
    assert [p["number"] for p in st["prs"]] == [7] and st["prs"][0]["repo"] == "me/proj"


def test_http_end_to_end_and_push_client(env):
    d = make(env)
    srv = fd.DashServer(("127.0.0.1", 0), d)
    import threading
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_port
    try:
        d.registry.dash_port = port
        url = fd.master_url(d.registry)
        assert url == f"http://laptop-ts:{port}"  # the registry's master and [dash] port
        base = f"http://127.0.0.1:{port}"
        ok, msg = fd.push(snap("laptop"), base)  # localhost, master node
        assert ok, msg
        ok, msg = fd.push(snap("alfred"), base)
        assert not ok and "403" in msg
        with urllib.request.urlopen(base + "/api/state") as r:
            assert json.load(r)["nodes"]["laptop"]["status"] == "ok"
        with urllib.request.urlopen(base + "/api/health") as r:
            assert json.load(r)["ok"] is True
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(urllib.request.Request(base + "/api/report", data=b"{", method="POST"))
        assert e.value.code == 400
    finally:
        srv.shutdown()
        srv.server_close()
