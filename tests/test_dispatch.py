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


# ---- step 2: the remote prepare script, run locally against a fake HOME ----
sys.path.insert(0, str(ROOT / "lib"))
import friday_fleet as ff  # noqa: E402
import json  # noqa: E402


def run_prepare(e, *, trusted=True, session=False, node_repos="~/work", base="main",
                precreate=None):
    home = e.tmp / "home"
    home.mkdir(exist_ok=True)
    (home / "bin").mkdir(exist_ok=True)
    tmux = home / "bin" / "tmux"
    tmux.write_text(f"#!/bin/sh\n{'exit 0' if session else 'exit 1'}\n")
    tmux.chmod(0o755)
    if trusted:
        (home / ".claude.json").write_text(json.dumps(
            {"projects": {str(home): {"hasTrustDialogAccepted": True}}}))
    if not (home / "friday").exists():
        subprocess.run(["git", "clone", "-q", str(e.plugin.parent / "plug.git"), str(home / "friday")],
                       check=True, capture_output=True)
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=e.plugin, capture_output=True,
                            text=True).stdout.strip()
    node = ff.Node("alfred", "worker", "me@alfred", repos=node_repos, plugin_dir="~/friday")
    origin = str(e.repo.parent / "proj.git")
    script = ff.prepare_script(node, "g1", "proj", precreate or origin, base, commit)
    env = {**e.env, "HOME": str(home), "PATH": f"{home / 'bin'}:{os.environ['PATH']}",
           "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    r = subprocess.run(["bash", "-s"], input=script, env=env, capture_output=True, text=True)
    return r, home, commit


def test_prepare_new_clone_worktree_from_base(env):
    r, home, commit = run_prepare(env)
    assert r.returncode == 0, r.stdout + r.stderr
    wt = home / "work" / "proj.friday" / "g1"
    assert f"FRIDAY_WORKTREE {wt}" in r.stdout
    git_out = lambda *a: subprocess.run(["git", "-C", str(wt), *a], capture_output=True, text=True).stdout.strip()
    assert git_out("branch", "--show-current") == "friday/g1"
    assert git_out("rev-parse", "HEAD") == git_out("rev-parse", "origin/main")
    assert git_out("config", "--get", "branch.friday/g1.merge") == ""  # --no-track
    plug = subprocess.run(["git", "-C", str(home / "friday"), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    assert plug == commit


def test_prepare_tracks_origin_goal_branch(env):
    git(env.repo, "switch", "-q", "-c", "friday/g1")
    (env.repo / "extra").write_text("e")
    git(env.repo, "add", "-A")
    git(env.repo, "commit", "-qm", "e")
    git(env.repo, "push", "-q", "origin", "friday/g1")
    r, home, _ = run_prepare(env)
    assert r.returncode == 0, r.stdout + r.stderr
    wt = home / "work" / "proj.friday" / "g1"
    assert (wt / "extra").exists()
    up = subprocess.run(["git", "-C", str(wt), "rev-parse", "--abbrev-ref", "friday/g1@{upstream}"],
                        capture_output=True, text=True).stdout.strip()
    assert up == "origin/friday/g1"


def test_prepare_refusals(env):
    r, *_ = run_prepare(env, trusted=False)
    assert r.returncode == ff.PREPARE_EXIT["untrusted"] and "FRIDAY_REFUSE untrusted" in r.stdout
    r, *_ = run_prepare(env, session=True)
    assert r.returncode == ff.PREPARE_EXIT["session"]


def test_prepare_reuse_clone_mismatch_and_collisions(env):
    r, home, _ = run_prepare(env)
    assert r.returncode == 0
    clone = home / "work" / "proj"
    marker = clone / "dirty"
    marker.write_text("keep")
    # worktree/branch already exist -> refuse
    r, *_ = run_prepare(env)
    assert r.returncode == ff.PREPARE_EXIT["worktree"]
    subprocess.run(["git", "-C", str(clone), "worktree", "remove", "--force",
                    str(home / "work" / "proj.friday" / "g1")], check=True, capture_output=True)
    r, *_ = run_prepare(env)
    assert r.returncode == ff.PREPARE_EXIT["branch"]
    assert marker.read_text() == "keep"  # existing checkout untouched
    # origin mismatch names both URLs
    r, *_ = run_prepare(env, precreate="/elsewhere/other.git")
    assert r.returncode == ff.PREPARE_EXIT["origin"]
    assert "/elsewhere/other.git" in r.stdout and "proj.git" in r.stdout


def test_launch_line_verbatim():
    import shlex
    node = ff.Node("alfred", "worker", "me@alfred", runtime="docker", repos="~/w", plugin_dir="/opt/my friday")
    line = ff.launch_line(node, "g1", "/w/proj.friday/g1", "laptop", ["g1-01", "g1-02"], "boss")
    run = ("Run the remaining directives of goal g1, in this order, each with the slash command shown:\n"
           "1. /friday:execute g1-01\n2. /friday:execute g1-02\n"
           "Start the next only when the previous ended done. Stop at the first that blocks.")
    report = ("When the directives of goal g1 are finished or one has blocked, send session boss exactly "
              "one message with SendMessage. If the goal landed, the message is "
              "`done g1 PR <url>` (the URL from the goal landing); after sending it, "
              "run `friday session-end --goal g1` and stop. If a directive blocked, it is "
              "`blocked g1 <id>: <reason>`; after sending it, do not run session-end and stay "
              "open. Send no other message.")
    q = shlex.quote
    assert line == ("tmux new -d -s friday-g1 -c /w/proj.friday/g1 env FRIDAY_RUNTIME=docker "
                    "FRIDAY_DISPATCHED_FROM=laptop claude --model opus --permission-mode auto "
                    "--remote-control --name g1.alfred --plugin-dir " + q("/opt/my friday") +
                    " --append-system-prompt " + q(report) + " " + q(run))
    assert shlex.split(line)[-1] == run and "@" not in "g1.alfred"


def test_launch_line_expands_tilde_plugin_dir():
    node = ff.Node("alfred", "worker", "me@alfred", repos="~/w", plugin_dir="~/my friday")
    line = ff.launch_line(node, "g1", "/w/g1", "laptop", ["g1-01"], "boss")
    assert '--plugin-dir "$HOME"/\'my friday\' ' in line


def test_dry_run_prints_launch_and_no_report_to(env):
    rc, out, err = dispatch(env, "--dry-run", "--node", "alfred", "--report-to", "me")
    assert rc == 0, err
    assert "--name g1.alfred" in out and "send session me " in out and "/friday:execute g1-01" in out
    assert "FRIDAY_WORKTREE" in out and "refuse()" in out  # the remote prepare script is printed too
    env.nodes.write_text(env.nodes.read_text().replace('report_to = "boss"\n', ""))
    rc, out, err = dispatch(env, "--dry-run")
    assert rc == 20 and "report_to" in err


# ---- step 4: the dispatch record on the master ----
FAKE_SSH_RUN = """#!/bin/sh
for a; do host=$a; shift; [ "$1" = bash ] && break; done
cat > "$FAKE_DIR/stdin-$host-$$"
cat "$FAKE_DIR/stdin-$host-$$" >> "$FAKE_DIR/all-$host"
echo FRIDAY_REACH ok
echo "FRIDAY_LOAD 0"
echo "FRIDAY_WORKTREE /abs/work/proj.friday/g1"
grep -q 'refuse()' "$FAKE_DIR/stdin-$host-$$" && exit "$(cat "$FAKE_DIR/exit-$host" 2>/dev/null || echo 0)"
exit 0
"""


def test_dispatch_records_jsonl_on_master_only(env):
    Path(env.env["FRIDAY_SSH"]).write_text(FAKE_SSH_RUN)
    state = env.tmp / "state"
    env.env["XDG_STATE_HOME"] = str(state)
    before = subprocess.run(["git", "status", "--porcelain"], cwd=env.repo, capture_output=True, text=True).stdout
    rc, out, err = dispatch(env, "--node", "alfred", "--report-to", "me")
    assert rc == 0, out + err
    lines = (state / "friday" / "dispatches.jsonl").read_text().splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=env.plugin, capture_output=True, text=True).stdout.strip()
    assert {k: rec[k] for k in rec if k != "time"} == {
        "goal": "g1", "directives": ["g1-01", "g1-02"], "repo": "proj", "node": "alfred",
        "tmux_session": "friday-g1", "worktree": "/abs/work/proj.friday/g1", "branch": "friday/g1",
        "source_ref": "origin/main", "plugin_commit": commit, "report_to": "me"}
    assert rec["time"]
    sent = (env.fake / "all-me@alfred").read_text()
    assert "tmux new -d -s friday-g1 -c /abs/work/proj.friday/g1" in sent
    # a second dispatch appends; the master's tree is unchanged
    assert dispatch(env, "--node", "alfred", "--report-to", "me")[0] == 0
    assert len((state / "friday" / "dispatches.jsonl").read_text().splitlines()) == 2
    assert subprocess.run(["git", "status", "--porcelain"], cwd=env.repo, capture_output=True, text=True).stdout == before


def test_refused_or_dry_run_records_nothing(env):
    Path(env.env["FRIDAY_SSH"]).write_text(FAKE_SSH_RUN)
    state = env.tmp / "state"
    env.env["XDG_STATE_HOME"] = str(state)
    assert dispatch(env, "--node", "alfred", "--report-to", "me", "--dry-run")[0] == 0
    (env.fake / "exit-me@alfred").write_text("31")
    assert dispatch(env, "--node", "alfred", "--report-to", "me")[0] == 31
    assert not (state / "friday" / "dispatches.jsonl").exists()


def test_prepare_trusts_worktree_keeping_other_keys(env):
    r, home, _ = run_prepare(env)
    assert r.returncode == 0, r.stdout + r.stderr
    wt = (home / "work" / "proj.friday" / "g1").resolve()
    assert f"FRIDAY_TRUSTED {wt}" in r.stdout
    data = json.loads((home / ".claude.json").read_text())
    assert data["projects"][str(wt)] == {"hasTrustDialogAccepted": True}
    assert data["projects"][str(home)] == {"hasTrustDialogAccepted": True}
    bak = json.loads((home / ".claude.json.friday-bak").read_text())
    assert str(wt) not in bak["projects"]


def test_prepare_untrusted_does_not_write(env):
    r, home, _ = run_prepare(env, trusted=False)
    assert r.returncode == 30
    assert not (home / ".claude.json").exists()


def test_prepare_trust_keeps_other_projects_and_keys_and_backs_up_once(env):
    home = env.tmp / "home"
    home.mkdir()
    orig = {"numStartups": 7, "theme": "dark",
            "projects": {str(home): {"hasTrustDialogAccepted": True, "allowedTools": ["x"]},
                         "/other": {"hasTrustDialogAccepted": False, "k": 1}}}
    (home / ".claude.json").write_text(json.dumps(orig))
    r, home, _ = run_prepare(env, trusted=False)
    assert r.returncode == 0, r.stdout + r.stderr
    wt = str((home / "work" / "proj.friday" / "g1").resolve())
    data = json.loads((home / ".claude.json").read_text())
    expect = json.loads(json.dumps(orig))
    expect["projects"][wt] = {"hasTrustDialogAccepted": True}
    assert data == expect
    bak = home / ".claude.json.friday-bak"
    assert json.loads(bak.read_text()) == orig
    # a second prepare (fresh worktree) must not overwrite the first backup
    subprocess.run(["git", "-C", str(home / "work" / "proj"), "worktree", "remove", "--force", wt],
                   check=True, capture_output=True)
    subprocess.run(["git", "-C", str(home / "work" / "proj"), "branch", "-D", "friday/g1"],
                   check=True, capture_output=True)
    r, _, _ = run_prepare(env, trusted=False)
    assert r.returncode == 0, r.stdout + r.stderr
    assert json.loads(bak.read_text()) == orig
    assert not list(home.glob(".claude.json.*tmp*"))


def test_prepare_untrusted_repos_refuses_without_backup(env):
    home = env.tmp / "home"
    home.mkdir()
    (home / ".claude.json").write_text(json.dumps({"projects": {"/other": {}}}))
    before = (home / ".claude.json").read_text()
    r, home, _ = run_prepare(env, trusted=False)
    assert r.returncode == 30
    assert (home / ".claude.json").read_text() == before
    assert not (home / ".claude.json.friday-bak").exists()


def test_repo_name_from_origin_not_folder(env):
    other = env.tmp / "friday-plugin"
    subprocess.run(["git", "clone", "-q", str(env.repo.parent / "proj.git"), str(other)],
                   check=True, capture_output=True)
    env.repo = other
    rc, out, err = dispatch(env, "--dry-run", "--node", "alfred", "--report-to", "me")
    assert rc == 0, err
    assert "proj.friday/g1" in out and "friday-plugin" not in out
    Path(env.env["FRIDAY_SSH"]).write_text(FAKE_SSH_RUN)
    state = env.tmp / "state"
    env.env["XDG_STATE_HOME"] = str(state)
    assert dispatch(env, "--node", "alfred", "--report-to", "me")[0] == 0
    rec = json.loads((state / "friday" / "dispatches.jsonl").read_text().splitlines()[0])
    assert rec["repo"] == "proj"


def test_dry_run_shows_trust_step(env):
    rc, out, err = dispatch(env, "--dry-run", "--node", "alfred", "--report-to", "me")
    assert rc == 0, err
    assert "FRIDAY_TRUSTED" in out and "hasTrustDialogAccepted" in out


# ---- fleet-07 step 4: dispatch cleans the target node first ----
FAKE_SSH_CLEAN = """#!/bin/sh
for a; do host=$a; shift; [ "$1" = bash ] && break; done
cat > "$FAKE_DIR/stdin-$host-$$"
echo "$host $(grep -q FRIDAY_WT "$FAKE_DIR/stdin-$host-$$" && echo inventory)\
$(grep -q 'refuse()' "$FAKE_DIR/stdin-$host-$$" && echo prepare)" >> "$FAKE_DIR/order"
if grep -q 'FRIDAY_WT' "$FAKE_DIR/stdin-$host-$$"; then
  [ -e "$FAKE_DIR/clean-fails" ] && { echo "inventory boom" >&2; exit 5; }
  echo "FRIDAY_STRAY folder=odd origin=proj path=/w/odd"
  exit 0
fi
echo FRIDAY_REACH ok
echo "FRIDAY_LOAD 0"
echo "FRIDAY_WORKTREE /abs/work/proj.friday/g1"
exit 0
"""


def test_dispatch_cleans_first_and_reports(env):
    Path(env.env["FRIDAY_SSH"]).write_text(FAKE_SSH_CLEAN)
    env.env["XDG_STATE_HOME"] = str(env.tmp / "state")
    rc, out, err = dispatch(env, "--node", "alfred", "--report-to", "me")
    assert rc == 0, out + err
    order = [l.split()[-1] for l in (env.fake / "order").read_text().splitlines() if l.split()[-1:] != ["me@alfred"]]
    assert order[:2] == ["inventory", "prepare"]
    assert "clean alfred: stray clone odd" in out and "remove by hand" in out
    assert out.index("clean alfred") < out.index("dispatched g1")


def test_dispatch_proceeds_when_clean_fails(env):
    Path(env.env["FRIDAY_SSH"]).write_text(FAKE_SSH_CLEAN)
    env.env["XDG_STATE_HOME"] = str(env.tmp / "state")
    (env.fake / "clean-fails").write_text("")
    rc, out, err = dispatch(env, "--node", "alfred", "--report-to", "me")
    assert rc == 0, out + err
    assert "clean alfred: failed (inventory boom); dispatching anyway" in out
    assert "dispatched g1 to alfred" in out


def test_nodes_clean_cli_runs_clean_and_dry_run(env):
    Path(env.env["FRIDAY_SSH"]).write_text(FAKE_SSH_CLEAN)
    for extra in ([], ["--dry-run"]):
        r = subprocess.run([sys.executable, str(FRIDAY), "nodes", "--clean", "alfred", *extra],
                           cwd=env.repo, env=env.env, capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr
        assert "clean alfred: stray clone odd" in r.stdout
    r = subprocess.run([sys.executable, str(FRIDAY), "nodes", "--clean", "nope"],
                       cwd=env.repo, env=env.env, capture_output=True, text=True)
    assert r.returncode == 1 and "no node named" in r.stdout
