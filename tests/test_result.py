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


def test_check_passes_and_fails(repo):
    ck = repo / "ck.bin"
    ck.write_bytes(b"w")
    assert friday(repo, "result", "write", "t-01", "--metric", "acc=0.93", "--metric", "tag=v1", "--file", "ck.bin").returncode == 0
    ok = friday(repo, "result", "check", "t-01", "--require", "acc >= 0.9", "--require", "tag == v1", "--require", "acc != 1", "--files")
    assert ok.returncode == 0, ok.stdout
    r = friday(repo, "result", "check", "t-01", "--require", "acc > 0.95", "--require", "nope == 1")
    assert r.returncode == 1 and "acc > 0.95" in r.stdout and "nope is not recorded" in r.stdout
    assert len(r.stdout.strip().splitlines()) == 2
    ck.write_bytes(b"changed")
    r = friday(repo, "result", "check", "t-01", "--files")
    assert r.returncode == 1 and "file changed: ck.bin" in r.stdout
    assert friday(repo, "result", "check", "t-01").returncode == 0
    ck.unlink()
    assert friday(repo, "result", "check", "t-01", "--files").returncode == 0


def test_check_missing_record(repo):
    r = friday(repo, "result", "check", "t-09")
    assert r.returncode == 1 and "no record" in r.stdout


def test_check_unrelated_commit(repo):
    assert friday(repo, "result", "write", "t-01").returncode == 0
    git(repo, "checkout", "-q", "--orphan", "other")
    git(repo, "commit", "-qm", "other", "--allow-empty")
    r = friday(repo, "result", "check", "t-01")
    assert r.returncode == 1 and "not an ancestor of HEAD" in r.stdout


def test_check_warns_when_verify_matches_hardware(repo):
    (repo / "docs" / "directives").mkdir(parents=True)
    (repo / "docs" / "goals").mkdir(parents=True)
    (repo / ".claude").mkdir()
    (repo / ".claude" / "friday.json").write_text(json.dumps({"hardware": {"gpu": ["train\\.py"]}}))
    (repo / "docs" / "goals" / "g.md").write_text("# g: goal\nStatus: approved\n\n## Directives\n- t-01\n")
    body = ("# t-01: x\nStatus: approved\nGoal: g\nNode: any\nDeliverable: code\nLand: goal\n"
            "Verify: python train.py --epochs 3\nHardware: none\n\n## Goal\nx\n\n## Steps\n1. a\n\n## Out of scope\n- b\n\n## Log\n")
    (repo / "docs" / "directives" / "t-01.md").write_text(body)
    r = friday(repo, "check", "t-01")
    assert "warning" in r.stdout and "matches hardware pattern `train\\.py`" in r.stdout and "friday result" in r.stdout
    (repo / "docs" / "directives" / "t-01.md").write_text(body.replace("python train.py --epochs 3", "friday result check t-01"))
    assert "hardware pattern" not in friday(repo, "check", "t-01").stdout
