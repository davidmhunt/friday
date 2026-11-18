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


# ---- friday nodes ----
import os
import subprocess

FRIDAY = ROOT / "bin" / "friday"


def test_example_parses_and_toml_ignored():
    reg = ff.load_nodes(ROOT / "nodes.example.toml")
    assert [n.role for n in reg.nodes.values()] == ["master", "worker", "target"]
    assert reg.nodes["alfred"].ssh == "david@alfred-ts" and reg.nodes["alfred"].repos == "~/Documents"
    r = subprocess.run(["git", "check-ignore", "nodes.toml"], cwd=ROOT, capture_output=True)
    assert r.returncode == 0


def _friday(tmp_path, nodes_text, *args, ssh_script=None):
    env = dict(os.environ, FRIDAY_NODES=str(tmp_path / "n.toml"))
    (tmp_path / "n.toml").write_text(nodes_text)
    if ssh_script:
        s = tmp_path / "fakessh"
        s.write_text(ssh_script)
        s.chmod(0o755)
        env["FRIDAY_SSH"] = str(s)
    return subprocess.run([sys.executable, str(FRIDAY), "nodes", *args], env=env,
                          capture_output=True, text=True, cwd=tmp_path)


def test_nodes_list(tmp_path):
    r = _friday(tmp_path, GOOD)
    assert r.returncode == 0
    lines = r.stdout.splitlines()
    assert str(tmp_path / "n.toml") in lines[0]
    assert len(lines) == 4 and "me@alfred" in lines[2] and "container" in lines[2]


def test_nodes_no_file(tmp_path):
    env = dict(os.environ, FRIDAY_NODES=str(tmp_path / "none"), HOME=str(tmp_path))
    r = subprocess.run([sys.executable, str(FRIDAY), "nodes"], env=env, capture_output=True, text=True)
    if (ROOT / "nodes.toml").exists():
        pytest.skip("real nodes.toml present")
    assert r.returncode != 0 and "nodes.example.toml" in r.stdout


FAKE = """#!/bin/bash
echo "$@" >> "$0.argv"; cat >> "$0.stdin"
case "$*" in
  *me@laptop*) printf 'FRIDAY_PROBE reach=ok\\nFRIDAY_PROBE claude=2.1 (Claude Code)\\nFRIDAY_PROBE tmux=ok\\nFRIDAY_PROBE git=ok\\nFRIDAY_PROBE plugin=ok\\nFRIDAY_PROBE friday=ok\\nFRIDAY_PROBE trust=ok\\nFRIDAY_PROBE workflow=ok\\nFRIDAY_PROBE auto=ok\\n';;
  *me@alfred*) exit 255;;
  *me@bot*) echo FRIDAY_PROBE reach=ok;;
esac
"""


def test_nodes_check_unreachable_worker_fails(tmp_path):
    r = _friday(tmp_path, GOOD, "--check", ssh_script=FAKE)
    assert r.returncode == 1
    assert "unreachable" in r.stdout and "me@alfred" in r.stdout
    assert "laptop" in r.stdout and "reachable" in r.stdout
    assert 'export PATH="$HOME/.local/bin' in (tmp_path / "fakessh.stdin").read_text()
    assert "BatchMode=yes" in (tmp_path / "fakessh.argv").read_text()


def test_nodes_check_untrusted_and_ready(tmp_path):
    fake = FAKE.replace("*me@alfred*) exit 255;;",
                        "*me@alfred*) printf 'FRIDAY_PROBE reach=ok\\nFRIDAY_PROBE claude=missing\\nFRIDAY_PROBE tmux=ok\\nFRIDAY_PROBE git=ok\\nFRIDAY_PROBE plugin=ok\\nFRIDAY_PROBE friday=ok\\nFRIDAY_PROBE trust=no\\n';;")
    r = _friday(tmp_path, GOOD, "--check", ssh_script=fake)
    assert r.returncode == 1
    assert "accept the trust prompt" in r.stdout and "install Claude Code" in r.stdout
    ok = GOOD.replace('[node.alfred]\nrole = "worker"', '[node.alfred]\nrole = "target"')
    ok = ok.replace('runtime = "container"\ntags = ["gpu"]\nrepos = "~/Documents"\nplugin_dir = "~/friday"\n', '')
    r = _friday(tmp_path, ok, "--check", ssh_script=FAKE)
    assert r.returncode == 0, r.stdout


def test_nodes_check_reports_missing_settings_prompts(tmp_path):
    base = "FRIDAY_PROBE reach=ok\\nFRIDAY_PROBE claude=2.1\\nFRIDAY_PROBE tmux=ok\\nFRIDAY_PROBE git=ok\\nFRIDAY_PROBE plugin=ok\\nFRIDAY_PROBE friday=ok\\nFRIDAY_PROBE trust=ok\\n"
    for extra, want, absent in [
            ("FRIDAY_PROBE workflow=no\\nFRIDAY_PROBE auto=no\\n", ["workflow prompt", "auto-mode prompt"], []),
            ("FRIDAY_PROBE workflow=ok\\nFRIDAY_PROBE auto=no\\n", ["auto-mode prompt"], ["workflow prompt"]),
            ("", ["workflow prompt", "auto-mode prompt"], [])]:
        fake = FAKE.replace("*me@alfred*) exit 255;;", f"*me@alfred*) printf '{base}{extra}';;")
        r = _friday(tmp_path, GOOD, "--check", ssh_script=fake)
        assert r.returncode == 1
        for w in want:
            assert f"{w}: run `friday nodes --setup alfred`" in r.stdout
        for w in absent:
            assert w not in r.stdout


def test_settings_probe_script_semantics(tmp_path):
    import subprocess as sp
    from importlib.machinery import SourceFileLoader
    script = SourceFileLoader("friday_bin", str(Path(__file__).resolve().parent.parent / "bin" / "friday")).load_module()._SETTINGS_PY
    for content, want in [(None, "no no"), ("{bad", "no no"),
                          ('{"skipWorkflowUsageWarning": true}', "ok no"),
                          ('{"skipWorkflowUsageWarning": true, "skipAutoPermissionPrompt": true}', "ok ok")]:
        home = tmp_path / ("h" + str(abs(hash(str(content)))))
        (home / ".claude").mkdir(parents=True)
        if content is not None:
            (home / ".claude" / "settings.json").write_text(content)
        out = sp.run([sys.executable, "-c", script], env={"HOME": str(home)}, capture_output=True, text=True).stdout
        vals = [l.split("=")[1] for l in out.splitlines()]
        assert " ".join(vals) == want


def test_nodes_check_ready_unreachable_untrusted_together(tmp_path):
    reg = GOOD + '[node.bert]\nrole = "worker"\nssh = "me@bert"\nrepos = "~/r"\nplugin_dir = "~/f"\n'
    fake = FAKE.replace("*me@bot*)", "*me@bert*) printf 'FRIDAY_PROBE reach=ok\\nFRIDAY_PROBE claude=2.1\\nFRIDAY_PROBE tmux=ok\\nFRIDAY_PROBE git=ok\\nFRIDAY_PROBE plugin=ok\\nFRIDAY_PROBE friday=ok\\nFRIDAY_PROBE trust=no\\n';;\n  *me@bot*)")
    r = _friday(tmp_path, reg, "--check", ssh_script=fake)
    assert r.returncode == 1
    out = r.stdout
    assert "unreachable" in out and "accept the trust prompt" in out
    argv = (tmp_path / "fakessh.argv").read_text().splitlines()
    assert len(argv) == 4  # one probe per node
    assert all(a.endswith("bash -s") for a in argv)
    assert (tmp_path / "fakessh.stdin").read_text().count('export PATH="$HOME/.local/bin:$PATH"') == 4


def test_nodes_check_reports_session_count(tmp_path):
    fake = FAKE.replace("FRIDAY_PROBE tmux=ok\\n", "FRIDAY_PROBE tmux=ok\\nFRIDAY_PROBE sessions=3\\n", 1)
    r = _friday(tmp_path, GOOD, "--check", ssh_script=fake)
    assert "3 friday-* sessions" in r.stdout
    assert "FRIDAY_PROBE sessions=" in (tmp_path / "fakessh.stdin").read_text()
    assert "grep -c '^friday-'" in (tmp_path / "fakessh.stdin").read_text()
