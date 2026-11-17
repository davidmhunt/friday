"""Tests for `friday dispatch` preconditions (step 1). Run: uv run --with pytest pytest -q tests/test_dispatch.py"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FRIDAY = ROOT / "bin" / "friday"
CODES = {"goal": 10, "format": 11, "directives": 12, "land-pr": 13, "unpushed": 14,
         "plugin": 15, "registry": 16, "route": 17, "node": 18, "unreachable": 19}

NODES = """
report_to = "boss"
[node.laptop]
role = "master"
ssh = "me@laptop"
repos = "~/src"
plugin_dir = "~/friday"
tags = ["a"]
[node.alfred]
role = "worker"
ssh = "me@alfred"
repos = "~/Documents"
plugin_dir = "~/friday"
tags = ["gpu"]
[node.beta]
role = "worker"
ssh = "me@beta"
repos = "~/Documents"
plugin_dir = "~/friday"
"""

FAKE_SSH = """#!/bin/sh
# fake ssh: last three args are <host> bash -s; state in $FAKE_DIR
for a; do host=$a; shift; [ "$1" = bash ] && break; done
cat >/dev/null
[ -e "$FAKE_DIR/down-$host" ] && exit 255
echo FRIDAY_REACH ok
echo "FRIDAY_LOAD $(cat "$FAKE_DIR/load-$host" 2>/dev/null || echo 0)"
"""

GOAL = """# g1: A goal
Status: approved
Base: main
Land: pr

## Goal
Do it.

## Directives
1. g1-01: first
2. g1-02: second

## Log
"""


def directive(did, status="approved", node="any", land="goal"):
    return f"""# {did}: Thing
Status: {status}
Goal: g1
Node: {node}
Deliverable: code
Land: {land}
Verify: true
Hardware: none

## Goal
Do it.

## Steps
1. Do the thing.

## Out of scope
- Nothing.

## Log
"""


def git(cwd, *a):
    subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True,
                   env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})


def make_repo(tmp, name, files):
    bare = tmp / f"{name}.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True)
    wd = tmp / name
    subprocess.run(["git", "clone", "-q", str(bare), str(wd)], check=True, capture_output=True)
    git(wd, "checkout", "-q", "-B", "main")
    for p, t in files.items():
        (wd / p).parent.mkdir(parents=True, exist_ok=True)
        (wd / p).write_text(t)
    (wd / "README").write_text("x")
    git(wd, "add", "-A")
    git(wd, "commit", "-qm", "init")
    git(wd, "push", "-q", "-u", "origin", "main")
    return wd


@pytest.fixture
def env(tmp_path):
    files = {"docs/goals/g1.md": GOAL,
             "docs/directives/g1-01.md": directive("g1-01"),
             "docs/directives/g1-02.md": directive("g1-02")}
    repo = make_repo(tmp_path, "proj", files)
    plugin = make_repo(tmp_path, "plug", {})
    fake = tmp_path / "ssh"
    fake.write_text(FAKE_SSH)
    fake.chmod(0o755)
    nodes = tmp_path / "nodes.toml"
    nodes.write_text(NODES)
    fd = tmp_path / "fake"
    fd.mkdir()
    e = {**os.environ, "FRIDAY_SSH": str(fake), "FRIDAY_NODES": str(nodes), "FAKE_DIR": str(fd),
         "FRIDAY_PLUGIN_ROOT": str(plugin)}
    return type("E", (), {"repo": repo, "plugin": plugin, "env": e, "fake": fd, "tmp": tmp_path,
                          "nodes": nodes})


def dispatch(e, *args):
    r = subprocess.run([sys.executable, str(FRIDAY), "dispatch", "--goal", "g1", *args],
                       cwd=e.repo, env=e.env, capture_output=True, text=True)
    return r.returncode, r.stdout, r.stderr


def commit_push(e, msg="edit"):
    git(e.repo, "add", "-A")
    git(e.repo, "commit", "-qm", msg)
    git(e.repo, "push", "-q", "origin", "main")


def edit(e, rel, text):
    (e.repo / rel).write_text(text)
    commit_push(e)


def test_ok_dry_run(env):
    rc, out, err = dispatch(env, "--dry-run")
    assert rc == 0, err
    assert "g1-01 g1-02" in out and "origin/main" in out and "dry run" in out


def test_goal_missing_or_not_approved(env):
    assert dispatch(env, "--dry-run")[0] == 0
    edit(env, "docs/goals/g1.md", GOAL.replace("approved", "draft"))
    assert dispatch(env, "--dry-run")[0] == CODES["goal"]


def test_format_errors(env):
    edit(env, "docs/directives/g1-02.md", directive("g1-02").replace("Verify: true\n", ""))
    assert dispatch(env, "--dry-run")[0] == CODES["format"]


def test_first_remaining_not_approved_and_done_skipped(env):
    edit(env, "docs/directives/g1-01.md", directive("g1-01", status="proposed"))
    rc, out, err = dispatch(env, "--dry-run")
    assert rc == CODES["directives"]
    edit(env, "docs/directives/g1-01.md", directive("g1-01", status="done"))
    rc, out, err = dispatch(env, "--dry-run")
    assert rc == 0, err
    assert "directives: g1-02" in out


def test_land_pr_refused(env):
    edit(env, "docs/directives/g1-02.md", directive("g1-02", land="pr"))
    assert dispatch(env, "--dry-run")[0] == CODES["land-pr"]


def test_files_not_pushed(env):
    (env.repo / "docs/directives/g1-02.md").write_text(directive("g1-02") + "\nmore\n")
    assert dispatch(env, "--dry-run")[0] == CODES["unpushed"]  # uncommitted
    git(env.repo, "commit", "-qam", "local")
    assert dispatch(env, "--dry-run")[0] == CODES["unpushed"]  # committed, not pushed


def test_source_ref_prefers_goal_branch(env):
    git(env.repo, "push", "-q", "origin", "main:friday/g1")
    rc, out, err = dispatch(env, "--dry-run")
    assert rc == 0, err
    assert "origin/friday/g1" in out
    edit(env, "docs/directives/g1-02.md", directive("g1-02") + "\nmore\n")  # main moves, goal branch not
    assert dispatch(env, "--dry-run")[0] == CODES["unpushed"]


def test_plugin_not_pushed(env):
    (env.plugin / "x").write_text("x")
    git(env.plugin, "add", "-A")
    git(env.plugin, "commit", "-qm", "local")
    assert dispatch(env, "--dry-run")[0] == CODES["plugin"]
    git(env.plugin, "push", "-q", "origin", "main")
    assert dispatch(env, "--dry-run")[0] == 0


def test_unreachable(env):
    for h in ("alfred", "beta"):
        (env.fake / f"down-me@{h}").write_text("")
    assert dispatch(env, "--dry-run")[0] == CODES["unreachable"]


def test_conflicting_node_lines(env):
    edit(env, "docs/directives/g1-01.md", directive("g1-01", node="host:alfred"))
    edit(env, "docs/directives/g1-02.md", directive("g1-02", node="host:beta"))
    rc, out, err = dispatch(env, "--dry-run")
    assert rc == CODES["route"]
    assert "g1-01" in err and "g1-02" in err
    rc, out, err = dispatch(env, "--dry-run", "--node", "beta")
    assert rc == 0, err
    assert "-> beta" in out


def test_node_lines_intersect(env):
    edit(env, "docs/directives/g1-01.md", directive("g1-01", node="tag:gpu"))
    rc, out, err = dispatch(env, "--dry-run")
    assert rc == 0, err
    assert "-> alfred" in out


def test_any_picks_fewer_sessions(env):
    (env.fake / "load-me@alfred").write_text("3")
    (env.fake / "load-me@beta").write_text("1")
    assert "-> beta" in dispatch(env, "--dry-run")[1]
    (env.fake / "load-me@beta").write_text("5")
    assert "-> alfred" in dispatch(env, "--dry-run")[1]


def test_node_override_unknown_or_target(env):
    assert dispatch(env, "--dry-run", "--node", "nope")[0] == CODES["node"]
