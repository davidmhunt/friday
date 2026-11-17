"""Tests for friday's node registry. Run: uv run --with pytest pytest -q tests/test_fleet.py"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib"))
import friday_fleet as ff  # noqa: E402

GOOD = """
report_to = "boss"
[node.laptop]
role = "master"
ssh = "me@laptop"
repos = "~/src"
plugin_dir = "~/friday"
[node.alfred]
role = "worker"
ssh = "me@alfred"
runtime = "container"
tags = ["gpu"]
repos = "~/Documents"
plugin_dir = "~/friday"
[node.bot]
role = "target"
ssh = "me@bot"
"""


def write(tmp_path, text):
    p = tmp_path / "nodes.toml"
    p.write_text(text)
    return p


def test_lookup_order(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / ".config/friday").mkdir(parents=True)
    cfg = home / ".config/friday/nodes.toml"
    cfg.write_text(GOOD)
    monkeypatch.setattr(Path, "home", lambda: home)
    root = tmp_path / "root"
    root.mkdir()
    monkeypatch.setattr(ff, "PLUGIN_ROOT", root)
    monkeypatch.delenv("FRIDAY_NODES", raising=False)
    assert ff.find_nodes_file() == cfg
    (root / "nodes.toml").write_text(GOOD)
    assert ff.find_nodes_file() == root / "nodes.toml"
    env = write(tmp_path, GOOD)
    monkeypatch.setenv("FRIDAY_NODES", str(env))
    assert ff.find_nodes_file() == env
    monkeypatch.setenv("FRIDAY_NODES", str(tmp_path / "missing"))
    assert ff.find_nodes_file() == root / "nodes.toml"


def test_load_good(tmp_path):
    reg = ff.load_nodes(write(tmp_path, GOOD))
    assert reg.report_to == "boss"
    assert list(reg.nodes) == ["laptop", "alfred", "bot"]
    a = reg.nodes["alfred"]
    assert (a.role, a.runtime, a.tags, a.launcher) == ("worker", "container", ["gpu"], "tmux")
    assert reg.nodes["bot"].repos == ""


@pytest.mark.parametrize("old,new,needle", [
    ('role = "worker"', 'role = "boss"', "node 'alfred': unknown 'role'"),
    ('runtime = "container"', 'runtime = "vm"', "node 'alfred': unknown 'runtime'"),
    ('ssh = "me@alfred"', 'ssh = "me@alfred"\nlauncher = "herdr"', "node 'alfred': unknown 'launcher'"),
    ('ssh = "me@alfred"', 'ssh = "me@laptop"', "node 'alfred': duplicate 'ssh'"),
    ('ssh = "me@bot"', '', "node 'bot': missing key 'ssh'"),
    ('repos = "~/Documents"\n', '', "node 'alfred': worker needs key 'repos'"),
    ('plugin_dir = "~/friday"\n[node.bot', '[node.bot', "needs key 'plugin_dir'"),
])
def test_validation_errors(tmp_path, old, new, needle):
    with pytest.raises(ff.RegistryError) as e:
        ff.load_nodes(write(tmp_path, GOOD.replace(old, new, 1)))
    assert needle in str(e.value)


def _reg(tmp_path, extra=""):
    return ff.load_nodes(write(tmp_path, GOOD + extra)).nodes


def test_route_any_lowest_load_and_ties(tmp_path):
    extra = '[node.bert]\nrole = "worker"\nssh = "me@bert"\nrepos = "~/r"\nplugin_dir = "~/f"\n'
    nodes = _reg(tmp_path, extra)
    assert ff.route("any", nodes, {})[0] == "alfred"  # tie: registry order
    assert ff.route("any", nodes, {"alfred": 2, "bert": 1})[0] == "bert"
    assert ff.route("any", nodes, {"alfred": 1, "bert": 1, "laptop": 0})[0] == "alfred"


def test_route_any_no_worker(tmp_path):
    nodes = {k: v for k, v in _reg(tmp_path).items() if v.role != "worker"}
    with pytest.raises(ff.RouteError, match="no worker"):
        ff.route("any", nodes, {})


def test_route_tag(tmp_path):
    nodes = _reg(tmp_path)
    assert ff.route("tag:gpu", nodes, {})[0] == "alfred"
    nodes["laptop"].tags.append("gpu")
    assert ff.route("tag:gpu", nodes, {"alfred": 3})[0] == "laptop"
    assert ff.route("tag:gpu", nodes, {"laptop": 3})[0] == "alfred"
    with pytest.raises(ff.RouteError, match="no node has tag 'nope'"):
        ff.route("tag:nope", nodes, {})


def test_route_tag_target_only(tmp_path):
    nodes = _reg(tmp_path)
    nodes["bot"].tags.append("arm")
    name, reason = ff.route("tag:arm", nodes, {})
    assert name == "laptop" and "over SSH" in reason and "bot" in reason


def test_route_host(tmp_path):
    nodes = _reg(tmp_path)
    assert ff.route("host:alfred", nodes, {"alfred": 9})[0] == "alfred"
    assert ff.route("host:laptop", nodes, {})[0] == "laptop"
    with pytest.raises(ff.RouteError, match="target"):
        ff.route("host:bot", nodes, {})
    with pytest.raises(ff.RouteError, match="no node named 'zzz'"):
        ff.route("host:zzz", nodes, {})
    with pytest.raises(ff.RouteError, match="expected"):
        ff.route("whatever", nodes, {})


def test_ssh_cmd(monkeypatch):
    node = ff.Node("alfred", "worker", "me@alfred")
    monkeypatch.delenv("FRIDAY_SSH", raising=False)
    argv, stdin = ff.ssh_cmd(node, "echo hi\n")
    assert argv == ["ssh", "-o", "ConnectTimeout=5", "-o", "BatchMode=yes",
                    "me@alfred", "bash", "-s"]
    assert stdin.startswith('export PATH="$HOME/.local/bin:$PATH"\n')
    assert stdin.endswith("echo hi\n")
    monkeypatch.setenv("FRIDAY_SSH", "/tmp/fake-ssh")
    assert ff.ssh_cmd(node, "x")[0][0] == "/tmp/fake-ssh"
