"""Tests for `friday status --json` (lib/friday_status.py) on a fixture tree, with fake
tmux, nvidia-smi and /proc. Run: uv run --with pytest --with pyyaml pytest -q tests/test_status_json.py"""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib"))
import friday_core as fc  # noqa: E402
import friday_status as fs  # noqa: E402
from helpers import private_bin  # noqa: E402

CLI = ROOT / "bin" / "friday"

DIRECTIVE = """# {id}: Make {id}
Status: {status}
Goal: core
Node: any
Deliverable: code
Land: goal
Verify: true
Hardware: none

## Goal
Do it.

## Steps
1. Do

## Out of scope
- nothing

## Log
"""
GOAL = """# core: The core goal
Status: approved
Base: main
Land: pr

## Goal
Do the core.

## Directives
1. core-01: First
2. core-02: Second

## Log
"""

GPU_LIST = ("0, GPU-aaa, NVIDIA RTX 4090, 37, 1024, 24564\n"
            "1, GPU-bbb, NVIDIA RTX 4090, [N/A], 0, 24564\n")
GPU_APPS = "GPU-aaa, 4242, python, 900\n"

SECRETS = ["sk-ant-api03-AbCdEf123456", "ghp_abcdefghijklmnop1234", "gho_abcdefghijklmnop1234",
           "AKIAIOSFODNN7EXAMPLE", "MIIEabcSECRETKEY", "hunter2xyz", "s3cr3tvalue", "bearerSECRET99"]
SECRET_PANE = "\n".join([
    "key sk-ant-api03-AbCdEf123456", "ghp_abcdefghijklmnop1234", "gho_abcdefghijklmnop1234",
    "id AKIAIOSFODNN7EXAMPLE", "-----BEGIN RSA PRIVATE KEY-----", "MIIEabcSECRETKEY",
    "-----END RSA PRIVATE KEY-----", "run --password=hunter2xyz", "curl 'u?token=s3cr3tvalue&x=1'",
    "Authorization: Bearer bearerSECRET99", "execute 3/4"])
WAIT_PANE = "some output\nRun a dynamic workflow?\n  1. Yes\n  2. No"


def git(*args, cwd):
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


def make_repo(path: Path, statuses=("approved", "done")):
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(path)], check=True)
    for k, v in (("user.name", "t"), ("user.email", "t@t")):
        git("config", k, v, cwd=path)
    git("remote", "add", "origin", "https://example.invalid/x.git", cwd=path)
    (path / "docs" / "directives").mkdir(parents=True)
    (path / "docs" / "goals").mkdir(parents=True)
    for i, s in enumerate(statuses, 1):
        did = f"core-0{i}"
        (path / "docs" / "directives" / f"{did}.md").write_text(DIRECTIVE.format(id=did, status=s))
    (path / "docs" / "goals" / "core.md").write_text(GOAL)
    git("add", ".", cwd=path)
    git("commit", "-qm", "init", cwd=path)


@pytest.fixture
def tree(tmp_path, monkeypatch):
    """repos/alpha (+ goal worktree alpha.friday/core) and repos/beta, a registry, fake proc."""
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    repos = tmp_path / "repos"
    make_repo(repos / "alpha")
    make_repo(repos / "beta", statuses=("proposed", "proposed"))
    wt = repos / "alpha.friday" / "core"
    wt.parent.mkdir()
    git("worktree", "add", "-q", "-b", "friday/core", str(wt), cwd=repos / "alpha")
    reg = tmp_path / "nodes.toml"
    reg.write_text(f'[node.n1]\nrole = "worker"\nssh = "n1"\nrepos = "{repos}"\nplugin_dir = "~/friday"\n')
    proc = tmp_path / "proc"
    proc.mkdir()
    (proc / "uptime").write_text("12345.67 999.0\n")
    (proc / "loadavg").write_text("0.50 1.25 2.00 1/100 999\n")
    (proc / "meminfo").write_text("MemTotal: 1000 kB\nMemFree: 100 kB\nMemAvailable: 400 kB\n")
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    shutil.copy(shutil.which("git"), bin_ / "git")
    monkeypatch.setenv("PATH", str(bin_))
    return type("T", (), {"tmp": tmp_path, "repos": repos, "wt": wt, "reg": reg, "proc": proc, "bin": bin_})


def fake_tmux(t, sessions: dict):
    """sessions: name -> (cwd, pane text)."""
    data = t.tmp / "tmuxdata"
    data.mkdir(exist_ok=True)
    rows = []
    for i, (name, (cwd, pane)) in enumerate(sessions.items()):
        rows.append(f"{name}\t1700000000\t{cwd}\t%{i}")
        (data / f"%{i}").write_text(pane)
    rows.append(f"other\t1700000000\t{t.tmp}\t%99")  # not a friday session
    (data / "list").write_text("\n".join(rows) + "\n")
    script = t.bin / "tmux"
    script.write_text(f'#!/bin/sh\nPATH=/usr/bin:/bin\ncase "$1" in\n list-panes) cat {data}/list;;\n'
                      f' capture-pane) while [ "$1" != "-t" ]; do shift; done; cat {data}/"$2";;\nesac\n')
    script.chmod(0o755)


def fake_smi(t, ok=True):
    script = t.bin / "nvidia-smi"
    (t.tmp / "gl").write_text(GPU_LIST)
    (t.tmp / "ga").write_text(GPU_APPS)
    script.write_text(f'#!/bin/sh\nPATH=/usr/bin:/bin\ncase "$1" in\n --query-gpu*) cat {t.tmp}/gl;;\n --query-compute-apps*) cat {t.tmp}/ga;;\nesac\n')
    script.chmod(0o755)


def snap(t, cwd=None):
    return fs.collect(cwd=cwd or t.repos / "alpha", proc_root=t.proc, registry_path=t.reg, node_name="n1")


def test_schema_and_repos(tree):
    s = snap(tree)
    assert fs.check_schema(s) == [] and s["schema"] == 1 and s["node"] == "n1"
    assert s["errors"] == []
    paths = [r["path"] for r in s["repos"]]
    assert set(paths) == {str(tree.repos / "alpha"), str(tree.wt), str(tree.repos / "beta")}
    alpha = next(r for r in s["repos"] if r["path"] == str(tree.repos / "alpha"))
    assert alpha["origin"] == "https://example.invalid/x.git" and alpha["branch"] == "main"
    g = alpha["goals"][0]
    assert g["id"] == "core" and g["status"] == "approved"
    assert [(d["id"], d["status"], d["deliverable"]) for d in g["directives"]] == \
        [("core-01", "approved", "code"), ("core-02", "done", "code")]
    wt = next(r for r in s["repos"] if r["path"] == str(tree.wt))
    assert wt["branch"] == "friday/core"
    beta = next(r for r in s["repos"] if r["path"].endswith("beta"))
    assert {d["status"] for d in beta["goals"][0]["directives"]} == {"proposed"}


def test_health_from_fake_proc(tree):
    h = snap(tree)["health"]
    assert h["uptime_s"] == 12345.67 and h["load"] == [0.5, 1.25, 2.0]
    assert h["mem"] == {"total": 1000 * 1024, "used": 600 * 1024}
    assert h["disk"]["total"] > 0 and h["disk"]["used"] is not None


def test_missing_proc_gives_nulls_and_errors(tree):
    shutil.rmtree(tree.proc)
    s = fs.collect(cwd=tree.repos / "alpha", proc_root=tree.proc, registry_path=tree.reg, node_name="n1")
    assert s["health"]["uptime_s"] is None and s["health"]["load"] is None
    assert s["health"]["mem"] == {"total": None, "used": None}
    assert {e["where"] for e in s["errors"]} >= {"health.uptime", "health.load", "health.mem"}
    assert fs.check_schema(s) == []


def test_gpus_present_and_absent(tree):
    assert snap(tree)["gpus"] == []
    fake_smi(tree)
    s = snap(tree)
    assert fs.check_schema(s) == []
    assert [g["name"] for g in s["gpus"]] == ["NVIDIA RTX 4090"] * 2
    assert s["gpus"][0]["util"] == 37 and s["gpus"][0]["mem"] == {"used": 1024, "total": 24564}
    assert s["gpus"][0]["processes"] == [{"pid": 4242, "name": "python", "mem": 900}]
    assert s["gpus"][1]["util"] is None and s["gpus"][1]["processes"] == []


def test_sessions_waiting_busy_and_tmux_absent(tree):
    assert snap(tree)["sessions"] == []  # tmux absent
    fc.write_marker(tree.wt, {"id": "core-01", "base": "abc", "host": "n1"})
    fake_tmux(tree, {"friday-core": (str(tree.wt), WAIT_PANE),
                     "friday-busy": (str(tree.repos / "beta"), "working\nexecute 3/4\n")})
    s = snap(tree)
    assert fs.check_schema(s) == []
    by = {x["name"]: x for x in s["sessions"]}
    assert set(by) == {"friday-core", "friday-busy"}  # `other` is not a friday session
    w, b = by["friday-core"], by["friday-busy"]
    assert w["waiting"] is True and "dynamic workflow" in w["waiting_line"]
    assert w["directive"] == "core-01" and w["goal"] == "core" and w["phase"] == "started" and w["step"] is None
    assert w["cwd"] == str(tree.wt) and w["created"] == 1700000000
    assert b["waiting"] is False and b["waiting_line"] is None
    assert b["phase"] == "execute" and b["step"] == "3/4" and b["goal"] == "busy" and b["directive"] is None


def test_snippet_redacts_every_pattern(tree):
    fake_tmux(tree, {"friday-x": (str(tree.repos / "beta"), SECRET_PANE)})
    s = snap(tree)
    sess = s["sessions"][0]
    out = json.dumps(s)
    for secret in SECRETS:
        assert secret not in out, secret
    assert fs.REDACTED in "\n".join(sess["snippet"])
    assert len(sess["snippet"]) <= fs.SNIPPET_LINES and sess["step"] == "3/4"


def test_leases_and_runs(tree):
    fc.take_lease("radar", "sess-1234", "flashing")
    for name, code in (("verify", "0"), ("flash", "3")):
        p = tree.repos / "beta" / "runs" / "core-01" / f"{name}.exit"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(code + "\n")
    (tree.repos / "beta" / "runs" / "core-01" / "junk.exit").write_text("not a number")
    s = snap(tree)
    assert fs.check_schema(s) == []
    assert [(l["resource"], l["session"], l["note"]) for l in s["leases"]] == [("radar", "sess-1234", "flashing")]
    runs = {r["name"]: r for r in s["runs"]}
    assert runs["verify"]["exit"] == 0 and runs["flash"]["exit"] == 3 and runs["junk"]["exit"] is None
    assert runs["verify"]["id"] == "core-01" and runs["verify"]["repo"].endswith("beta")


def test_runs_capped_at_ten_newest(tree):
    d = tree.repos / "beta" / "runs" / "core-01"
    d.mkdir(parents=True)
    now = time.time()
    for i in range(14):
        p = d / f"r{i}.exit"
        p.write_text("0")
        os.utime(p, (now - 1000 + i, now - 1000 + i))
    names = [r["name"] for r in snap(tree)["runs"]]
    assert len(names) == 10 and names[0] == "r13" and "r3" not in names


def test_broken_directive_is_an_error_entry(tree):
    (tree.repos / "beta" / "docs" / "directives" / "core-01.md").write_bytes(b"\xff\xfe\x00bad")
    s = snap(tree)
    assert fs.check_schema(s) == []
    assert any(e["where"].endswith("core-01.md") for e in s["errors"])
    assert any(r["path"].endswith("beta") for r in s["repos"])  # the rest still reported


def test_check_schema_rejects_bad_snapshot(tree):
    s = snap(tree)
    del s["health"]["load"]
    s["gpus"] = [{"name": 5}]
    assert len(fs.check_schema(s)) >= 2


def run_cli(t, *args):
    env = {**os.environ, "PATH": os.environ["PATH"] + os.pathsep + str(private_bin(t.tmp / "pybin")),
           "FRIDAY_NODES": str(t.reg),
           "HOME": str(t.tmp / "home"),  # hermetic: never read the real ~/.config/friday/node.toml
           "FRIDAY_NODE_FILE": str(t.tmp / "no-node.toml")}
    return subprocess.run([sys.executable, str(CLI), *args], cwd=t.repos / "alpha", capture_output=True,
                          text=True, env=env)


def test_cli_json_matches_schema_and_writes_nothing(tree):
    before = subprocess.run(["git", "-C", str(tree.repos / "alpha"), "status", "--porcelain"],
                            capture_output=True, text=True).stdout
    r = run_cli(tree, "status", "--json")
    assert r.returncode == 0, r.stderr
    s = json.loads(r.stdout)
    assert fs.check_schema(s) == []
    assert any(x["path"].endswith("alpha") for x in s["repos"])
    after = subprocess.run(["git", "-C", str(tree.repos / "alpha"), "status", "--porcelain"],
                           capture_output=True, text=True).stdout
    assert before == after


def test_cli_status_node_flag_names_the_snapshot(tree):
    r = run_cli(tree, "status", "--json", "--node", "boxy")
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["node"] == "boxy"


def test_plain_status_unchanged(tree):
    r = run_cli(tree, "status")
    assert r.returncode == 0, r.stderr
    out = r.stdout.splitlines()
    assert out[0].startswith("goal core  approved  base main  1/2")
    assert out[1].split()[:2] == ["core-01", "approved"] and out[2].split()[:2] == ["core-02", "done"]
    assert "active here: none" in r.stdout and not r.stdout.lstrip().startswith("{")


def test_node_is_registry_name_when_matched_by_ssh(tree):
    import socket
    tree.reg.write_text(f'[node.gpu1]\nrole = "worker"\nssh = "{socket.gethostname()}"\n'
                        f'repos = "{tree.repos}"\nplugin_dir = "~/friday"\n')
    s = fs.collect(cwd=tree.repos / "alpha", proc_root=tree.proc, registry_path=tree.reg)
    assert s["node"] == "gpu1"
    assert s["host"] == socket.gethostname()


def test_status_creates_no_lease_dir(tree):
    state = tree.tmp / "state"
    assert not state.exists()
    snap(tree)
    assert not (state / "friday").exists()
