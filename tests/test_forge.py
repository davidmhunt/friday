"""forge(): URL forms, host recognition, the `forge` config override, the `Land: pr` check warnings and
compare URLs for both forges. glab is always a fake (FRIDAY_GLAB); no test reaches a real forge."""
import importlib.machinery
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib"))
import friday_core as fc  # noqa: E402

DIRECTIVE = """# core-01: Make the thing
Status: approved
Goal: core
Node: any
Deliverable: code
Land: pr
Verify: test -f ok.txt
Hardware: none

## Goal
Make it.

## Steps
1. Create ok.txt

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
1. core-01: Make the thing

## Log
"""


@pytest.fixture
def glab_env(tmp_path, monkeypatch):
    """FRIDAY_GLAB points at a fake glab that accepts `auth status --hostname` for hosts in GLAB_HOSTS."""
    fake = tmp_path / "bin" / "glab"
    fake.parent.mkdir()
    fake.write_text('#!/bin/sh\n[ "$1 $2 $3" = "auth status --hostname" ] || exit 2\n'
                    'for h in $GLAB_HOSTS; do [ "$h" = "$4" ] && exit 0; done\nexit 1\n')
    fake.chmod(0o755)
    monkeypatch.setenv("FRIDAY_GLAB", str(fake))
    monkeypatch.setenv("GLAB_HOSTS", "")
    return fake


def make_repo(path, origin=None, cfg=None):
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(path)], check=True)
    if origin:
        subprocess.run(["git", "-C", str(path), "remote", "add", "origin", origin], check=True)
    if cfg is not None:
        (path / ".claude").mkdir()
        (path / ".claude" / "friday.json").write_text(json.dumps(cfg))
    return path


def cli_mod():
    loader = importlib.machinery.SourceFileLoader("friday_cli", str(ROOT / "bin" / "friday"))
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader("friday_cli", loader))
    loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("origin,kind,host,slug", [
    ("git@github.com:o/r.git", "github", "github.com", "o/r"),
    ("https://github.com/o/r.git", "github", "github.com", "o/r"),
    ("https://github.com/o/r", "github", "github.com", "o/r"),
    ("git@gitlab.com:o/r.git", "gitlab", "gitlab.com", "o/r"),
    ("https://gitlab.com/o/r.git", "gitlab", "gitlab.com", "o/r"),
    ("git@gitlab.lab.example.edu:grp/sub/deep/repo.git", "gitlab", "gitlab.lab.example.edu", "grp/sub/deep/repo"),
    ("https://gitlab.lab.example.edu/grp/sub/repo.git", "gitlab", "gitlab.lab.example.edu", "grp/sub/repo"),
    ("ssh://git@gitlab.lab.example.edu:2222/grp/sub/repo.git", "gitlab", "gitlab.lab.example.edu", "grp/sub/repo"),
    ("ssh://git@github.com:22/o/r.git", "github", "github.com", "o/r"),
])
def test_forge_url_forms(tmp_path, glab_env, origin, kind, host, slug):
    f = fc.forge(make_repo(tmp_path / "r", origin))
    assert f == {"kind": kind, "host": host, "slug": slug, "web": f"https://{host}"}


def test_unknown_host_is_none(tmp_path, glab_env):
    f = fc.forge(make_repo(tmp_path / "r", "git@code.example.org:grp/repo.git"))
    assert f["kind"] == "none" and f["host"] == "code.example.org" and f["slug"] == "grp/repo"


def test_host_without_gitlab_in_name_recognised_through_glab(tmp_path, glab_env, monkeypatch):
    monkeypatch.setenv("GLAB_HOSTS", "code.example.org")
    f = fc.forge(make_repo(tmp_path / "r", "ssh://git@code.example.org:2222/grp/sub/repo.git"))
    assert f == {"kind": "gitlab", "host": "code.example.org", "slug": "grp/sub/repo",
                 "web": "https://code.example.org"}


def test_missing_glab_leaves_unknown_host_none(tmp_path, monkeypatch):
    monkeypatch.setenv("FRIDAY_GLAB", str(tmp_path / "no-such-glab"))
    assert fc.forge(make_repo(tmp_path / "r", "git@code.example.org:grp/repo.git"))["kind"] == "none"


def test_no_origin_and_local_path_are_none(tmp_path, glab_env):
    assert fc.forge(make_repo(tmp_path / "a"))["kind"] == "none"
    assert fc.forge(make_repo(tmp_path / "b", "/tmp/origin.git"))["kind"] == "none"
    assert fc.forge(None)["kind"] == "none"


@pytest.mark.parametrize("origin,override,kind", [
    ("git@github.com:o/r.git", "none", "none"),
    ("git@github.com:o/r.git", "gitlab", "gitlab"),
    ("git@gitlab.com:o/r.git", "github", "github"),
    ("git@gitlab.com:o/r.git", "none", "none"),
    ("git@code.example.org:grp/r.git", "gitlab", "gitlab"),
    ("git@code.example.org:grp/r.git", "github", "github"),
    (None, "github", "github"),
])
def test_config_override_wins(tmp_path, glab_env, origin, override, kind):
    f = fc.forge(make_repo(tmp_path / "r", origin, {"forge": override}))
    assert f["kind"] == kind
    if origin:
        assert f["slug"] and f["host"]


def test_invalid_forge_key_is_a_check_error_and_ignored(tmp_path, glab_env):
    r = make_repo(tmp_path / "r", "git@github.com:o/r.git", {"forge": "bitbucket"})
    assert fc.forge(r)["kind"] == "github"
    issues = fc.config_issues(r)
    assert any(i.level == "error" and "forge" in i.message and "bitbucket" in i.message for i in issues)


# ---------------------------------------------------------------- friday check warnings
def check_repo_with_land(tmp_path, origin, cfg=None, goal=GOAL, directive=DIRECTIVE):
    r = make_repo(tmp_path / "r", origin, cfg)
    (r / "docs" / "directives").mkdir(parents=True)
    (r / "docs" / "directives" / "core-01.md").write_text(directive)
    (r / "docs" / "goals").mkdir(parents=True)
    (r / "docs" / "goals" / "core.md").write_text(goal)
    return [i for i in fc.check_repo(r) if "Land: pr" in i.message]


def test_check_warns_once_per_goal_when_forge_none(tmp_path, glab_env):
    w = check_repo_with_land(tmp_path, None)
    assert len(w) == 1 and w[0].level == "warning"
    assert "core" in w[0].message and "forge" in w[0].message and "Land: push" in w[0].message


def test_check_warns_for_directive_only_land_pr(tmp_path, glab_env):
    w = check_repo_with_land(tmp_path, None, goal=GOAL.replace("Land: pr", "Land: goal"))
    assert len(w) == 1


def test_check_silent_without_land_pr(tmp_path, glab_env):
    w = check_repo_with_land(tmp_path, None, goal=GOAL.replace("Land: pr", "Land: goal"),
                             directive=DIRECTIVE.replace("Land: pr\n", "Land: none\n"))
    assert w == []


def test_check_silent_on_github(tmp_path, glab_env):
    assert check_repo_with_land(tmp_path, "git@github.com:o/r.git") == []


def test_check_silent_when_config_names_forge(tmp_path, glab_env):
    assert check_repo_with_land(tmp_path, None, {"forge": "github"}) == []


def test_check_warns_on_gitlab_without_glab(tmp_path, monkeypatch):
    monkeypatch.setenv("FRIDAY_GLAB", str(tmp_path / "no-such-glab"))
    w = check_repo_with_land(tmp_path, "git@gitlab.com:o/r.git")
    assert len(w) == 1 and w[0].level == "warning" and "glab" in w[0].message and "Land: push" in w[0].message


def test_check_silent_on_gitlab_with_glab(tmp_path, glab_env):
    assert check_repo_with_land(tmp_path, "git@gitlab.com:o/r.git") == []


# ---------------------------------------------------------------- compare URLs
@pytest.mark.parametrize("origin,cfg,expected", [
    ("git@github.com:o/r.git", None, "https://github.com/o/r/compare/main...friday/x?expand=1"),
    ("git@gitlab.com:o/r.git", None, "https://gitlab.com/o/r/-/compare/main...friday/x"),
    ("ssh://git@gitlab.lab.example.edu:2222/grp/sub/r.git", None,
     "https://gitlab.lab.example.edu/grp/sub/r/-/compare/main...friday/x"),
    ("git@code.example.org:grp/r.git", {"forge": "gitlab"},
     "https://code.example.org/grp/r/-/compare/main...friday/x"),
    ("git@code.example.org:grp/r.git", None, None),
    ("/tmp/origin.git", None, None),
])
def test_compare_url(tmp_path, glab_env, origin, cfg, expected):
    assert cli_mod()._compare_url(make_repo(tmp_path / "r", origin, cfg), "main", "friday/x") == expected
