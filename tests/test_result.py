"""friday result: write records a run in results/<id>.json."""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FRIDAY = ROOT / "bin" / "friday"


def git(cwd, *a):
    subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    r = tmp_path / "r"
    r.mkdir()
    git(r, "init", "-q")
    git(r, "config", "user.email", "t@t")
    git(r, "config", "user.name", "t")
    (r / "a.txt").write_text("a\n")
    git(r, "add", "-A")
    git(r, "commit", "-qm", "init")
    nf = tmp_path / "node.toml"
    nf.write_text('name = "alfred"\n')
    monkeypatch.setenv("FRIDAY_NODE_FILE", str(nf))
    return r


def friday(repo, *a):
    return subprocess.run([sys.executable, str(FRIDAY), *a], cwd=repo, capture_output=True, text=True)


def test_write_records_metrics_files_commit_node(repo):
    (repo / "runs" / "x").mkdir(parents=True)
    ck = repo / "runs" / "x" / "ck.bin"
    ck.write_bytes(b"weights")
    r = friday(repo, "result", "write", "t-01", "--metric", "acc=0.93", "--metric", "n=5", "--metric", "tag=v1",
               "--file", "runs/x/ck.bin", "--cmd", "python train.py", "--note", "first")
    assert r.returncode == 0, r.stderr
    rec = json.loads((repo / "results" / "t-01.json").read_text())
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True).stdout.strip()
    assert rec["metrics"] == {"acc": 0.93, "n": 5, "tag": "v1"}
    assert rec["files"] == [{"path": "runs/x/ck.bin", "sha256": hashlib.sha256(b"weights").hexdigest(), "size": 7}]
    assert rec["cmd"] == "python train.py" and rec["note"] == "first"
    assert rec["commit"] == head and rec["dirty"] is False
    assert rec["node"] == "alfred" and rec["time"].endswith("Z")


def test_dirty_tree_is_recorded(repo):
    (repo / "a.txt").write_text("changed\n")
    assert friday(repo, "result", "write", "t-01").returncode == 0
    assert json.loads((repo / "results" / "t-01.json").read_text())["dirty"] is True


def test_missing_file_and_bad_metric_fail(repo):
    r = friday(repo, "result", "write", "t-01", "--file", "nope.bin")
    assert r.returncode == 1 and "file not found: nope.bin" in r.stderr
    r = friday(repo, "result", "write", "t-01", "--metric", "oops")
    assert r.returncode == 1 and "K=V" in r.stderr
    assert not (repo / "results" / "t-01.json").exists()
