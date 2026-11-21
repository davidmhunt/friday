"""On GitLab, `friday land --goal` opens or finds a merge request with glab (FRIDAY_GLAB), never gh.
Run: uv run --with pytest --with pyyaml pytest -q tests/test_land_gitlab.py"""
import json
import sys

import pytest

from test_friday import cli, done_goal, grepo2, _git  # noqa: F401  (fixtures)

FAKE_GLAB = """#!{py}
import json, sys
argv = sys.argv[1:]
with open({log!r}, "a") as f:
    f.write(json.dumps(argv) + "\\n")
if argv[:2] == ["auth", "status"]:
    sys.exit({auth})
if argv[:2] == ["mr", "list"]:
    print({listing!r})
elif argv[:2] == ["mr", "create"]:
    print("Creating merge request\\nhttps://gitlab.example.com/o/r/-/merge_requests/7")
"""


def _setup(repo, origin, tmp_path, monkeypatch, url="git@gitlab.example.com:o/r.git", auth=0, listing="[]"):
    _git(repo, "remote", "set-url", "origin", url)
    ssh = tmp_path / "fakessh"
    ssh.write_text(f"#!/bin/sh\nexec sh -c \"$(printf '%s' \"$2\" | sed \"s#'[^']*'#'{origin}'#\")\"\n")
    ssh.chmod(0o755)
    monkeypatch.setenv("GIT_SSH_COMMAND", str(ssh))
    cfg = repo / ".claude" / "friday.json"
    cfg.write_text(json.dumps({**json.loads(cfg.read_text()), "forge": "gitlab"}))
    _git(repo, "add", "-A")
    _git(repo, "commit", "--no-verify", "-qm", "gitlab forge")
    log, ghlog = tmp_path / "glab.log", tmp_path / "gh.log"
    glab = tmp_path / "glab"
    glab.write_text(FAKE_GLAB.format(py=sys.executable, log=str(log), auth=auth, listing=listing))
    glab.chmod(0o755)
    gh = tmp_path / "gh"
    gh.write_text(f"#!/bin/sh\necho \"$@\" >> {ghlog}\nexit 0\n")
    gh.chmod(0o755)
    monkeypatch.setenv("FRIDAY_GLAB", str(glab))
    monkeypatch.setenv("FRIDAY_GH", str(gh))
    return log, ghlog


def _calls(log):
    return [json.loads(l) for l in log.read_text().splitlines()] if log.exists() else []


def _opt(argv, flag):
    return argv[argv.index(flag) + 1]


def test_creates_mr_with_branches_title_and_body(done_goal, tmp_path, monkeypatch):
    repo, origin = done_goal
    log, ghlog = _setup(repo, origin, tmp_path, monkeypatch)
    r = cli(repo, "land", "--goal", "core")
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.strip().splitlines()[-1] == "PR: https://gitlab.example.com/o/r/-/merge_requests/7"
    creates = [c for c in _calls(log) if c[:2] == ["mr", "create"]]
    assert len(creates) == 1
    c = creates[0]
    assert _opt(c, "--source-branch") == "friday/core" and _opt(c, "--target-branch") == "main"
    assert _opt(c, "--title").startswith("core: ")
    body = _opt(c, "--description")
    assert "| core-01 |" in body and "| core-02 |" in body and "no gaps" in body
    assert "--yes" in c
    assert not ghlog.exists()


def test_existing_mr_is_found_not_duplicated(done_goal, tmp_path, monkeypatch):
    repo, origin = done_goal
    url = "https://gitlab.example.com/o/r/-/merge_requests/3"
    log, ghlog = _setup(repo, origin, tmp_path, monkeypatch, listing=json.dumps([{"web_url": url}]))
    r = cli(repo, "land", "--goal", "core")
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.strip().splitlines()[-1] == f"PR: {url}"
    calls = _calls(log)
    lst = [c for c in calls if c[:2] == ["mr", "list"]]
    assert lst and _opt(lst[0], "--source-branch") == "friday/core"
    assert not [c for c in calls if c[:2] == ["mr", "create"]]
    assert not ghlog.exists()


def test_not_signed_in_gives_exit_5_with_compare(done_goal, tmp_path, monkeypatch):
    repo, origin = done_goal
    log, ghlog = _setup(repo, origin, tmp_path, monkeypatch, auth=1)
    r = cli(repo, "land", "--goal", "core")
    assert r.returncode == 5, r.stdout + r.stderr
    assert "MR not opened: " in r.stdout
    assert r.stdout.strip().splitlines()[-1] == "COMPARE: https://gitlab.example.com/o/r/-/compare/main...friday/core"
    calls = _calls(log)
    assert calls and calls[0] == ["auth", "status", "--hostname", "gitlab.example.com"]
    assert not [c for c in calls if c[0] == "mr"]
    assert not ghlog.exists()


def test_glab_not_installed_gives_exit_5(done_goal, tmp_path, monkeypatch):
    repo, origin = done_goal
    _, ghlog = _setup(repo, origin, tmp_path, monkeypatch)
    monkeypatch.setenv("FRIDAY_GLAB", "/nonexistent/glab")
    r = cli(repo, "land", "--goal", "core")
    assert r.returncode == 5, r.stdout + r.stderr
    assert r.stdout.strip().splitlines()[-1].startswith("COMPARE: https://gitlab.example.com/o/r/-/compare/")
    assert not ghlog.exists()


@pytest.mark.parametrize("url,host,slug", [
    ("git@git.corp.example:team/proj.git", "git.corp.example", "team/proj"),
    ("git@gitlab.example.com:grp/sub/deep/r.git", "gitlab.example.com", "grp/sub/deep/r"),
    ("ssh://git@gl.corp.example/a/b/c.git", "gl.corp.example", "a/b/c"),
])
def test_self_hosted_and_nested_group_reach_glab_as_dash_r(done_goal, tmp_path, monkeypatch, url, host, slug):
    repo, origin = done_goal
    log, ghlog = _setup(repo, origin, tmp_path, monkeypatch, url=url)
    r = cli(repo, "land", "--goal", "core")
    assert r.returncode == 0, r.stdout + r.stderr
    calls = _calls(log)
    assert calls[0] == ["auth", "status", "--hostname", host]
    mr = [c for c in calls if c[0] == "mr"]
    assert [c[1] for c in mr] == ["list", "create"]
    for c in mr:
        assert _opt(c, "-R") == f"{host}/{slug}"
    assert not ghlog.exists()
