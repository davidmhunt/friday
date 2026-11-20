"""On GitLab, merged detection, the status pr line and the dash PR list use glab (a fake one here);
GitHub repos keep using gh. Run: uv run --with pytest --with pyyaml pytest -q tests/test_forge_status.py"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FRIDAY = ROOT / "bin" / "friday"
sys.path.insert(0, str(ROOT / "lib"))
import friday_dash as fd  # noqa: E402
import friday_fleet as ff  # noqa: E402
import friday_status as fs  # noqa: E402
from helpers import private_bin  # noqa: E402
from test_dash_state import Clock, make, snap  # noqa: E402

TOKEN = "glpat-secret-token"
GL_URL = "git@gitlab.example.com:grp/proj.git"


def script(path, body):
    path.write_text(f"#!{sys.executable}\nimport json, os, sys\nargv = sys.argv[1:]\n{body}")
    path.chmod(0o755)
    return str(path)


def repo(tmp_path, url):
    r = tmp_path / "repo"
    r.mkdir()
    subprocess.run(["git", "init", "-q", str(r)], check=True)
    subprocess.run(["git", "-C", str(r), "remote", "add", "origin", url], check=True)
    return r


def fake_glab(tmp_path, listing):
    log = tmp_path / "glab.log"
    return script(tmp_path / "glab", f"open({str(log)!r}, 'a').write(json.dumps(argv) + '\\n')\n"
                  f"print({json.dumps(listing)!r})\n"), log


def runner(stdout="[]", rc=0, calls=None):
    def run(argv, **kw):
        if calls is not None:
            calls.append(argv)
        return subprocess.CompletedProcess(argv, rc, stdout, "")
    return run


# ---------------------------------------------------------------- merged detection
def test_pr_merged_uses_glab_on_gitlab(monkeypatch):
    monkeypatch.delenv("FRIDAY_GLAB", raising=False)
    calls = []
    assert ff.pr_merged(GL_URL, "core", runner('[{"iid": 3}]', calls=calls)) is True
    assert calls == [["glab", "mr", "list", "--merged", "--source-branch", "friday/core", "--output", "json",
                      "-R", "gitlab.example.com/grp/proj"]]
    assert ff.pr_merged(GL_URL, "core", runner("[]")) is False


def test_pr_merged_glab_missing_or_failing_is_none():
    def missing(argv, **kw):
        raise FileNotFoundError("glab")
    assert ff.pr_merged(GL_URL, "core", missing) is None
    assert ff.pr_merged(GL_URL, "core", runner("", rc=1)) is None


def test_pr_merged_and_decide_clean_use_forge_kind_for_self_hosted_host():
    url = "git@git.corp.example:grp/proj.git"
    assert ff.url_forge_tool(url) == "gh"
    assert ff.url_forge_tool(url, "gitlab") == "glab"
    calls = []
    assert ff.pr_merged(url, "core", runner('[{"iid": 3}]', calls=calls), kind="gitlab") is True
    assert calls[0][:3] == ["glab", "mr", "list"]
    inv = {"worktrees": [{"repo": "proj", "goal": "core", "path": "/w", "goalstatus": "done"}], "stray": []}
    calls.clear()
    plan = ff.decide_clean(inv, {"proj": url}, runner('[{"iid": 3}]', calls=calls), have_gh=True,
                           forge_kinds={"proj": "gitlab"})
    assert [w["why"] for w in plan["remove"]] == ["PR merged"] and calls[0][0] == "glab"


def test_pr_merged_github_unchanged():
    calls = []
    assert ff.pr_merged("git@github.com:me/proj.git", "core", runner('[{"number": 1}]', calls=calls)) is True
    assert calls == [["gh", "pr", "list", "-R", "me/proj", "--state", "merged", "--head", "friday/core",
                      "--json", "number"]]


# ---------------------------------------------------------------- status pr line
@pytest.mark.parametrize("state,want", [("opened", "open"), ("merged", "merged"), ("closed", "closed")])
def test_goal_pr_on_gitlab(tmp_path, state, want):
    r = repo(tmp_path, GL_URL)
    glab, log = fake_glab(tmp_path, [{"iid": 4, "state": state, "web_url": "https://gitlab.example.com/grp/proj/-/merge_requests/4"}])
    gh = script(tmp_path / "gh", "sys.exit(9)\n")
    assert fs.goal_pr(r, "core", gh, glab) == (want, "https://gitlab.example.com/grp/proj/-/merge_requests/4")
    (c,) = [json.loads(l) for l in log.read_text().splitlines()]
    assert c[:2] == ["mr", "list"] and c[c.index("--source-branch") + 1] == "friday/core"


def test_goal_pr_gitlab_no_mr_is_none_and_missing_glab_is_unknown(tmp_path, monkeypatch):
    r = repo(tmp_path, GL_URL)
    glab, _ = fake_glab(tmp_path, [])
    assert fs.goal_pr(r, "core", None, glab) == ("none", None)
    monkeypatch.delenv("FRIDAY_GLAB", raising=False)
    monkeypatch.setenv("PATH", str(private_bin(tmp_path / "pybin")))
    assert fs.goal_pr(r, "core", None, None) is None


def test_goal_pr_forge_none_is_none(tmp_path):
    r = repo(tmp_path, GL_URL)
    (r / ".claude").mkdir()
    (r / ".claude" / "friday.json").write_text('{"forge": "none"}')
    assert fs.goal_pr(r, "core", None, None) == ("none", None)


def test_goal_pr_github_uses_gh(tmp_path):
    r = repo(tmp_path, "git@github.com:me/proj.git")
    log = tmp_path / "gh.log"
    gh = script(tmp_path / "gh", f"open({str(log)!r}, 'a').write(json.dumps(argv) + '\\n')\n"
                "print(json.dumps([{'number': 2, 'state': 'MERGED', 'url': 'https://github.com/me/proj/pull/2'}]))\n")
    glab = script(tmp_path / "glab", "sys.exit(9)\n")
    assert fs.goal_pr(r, "core", gh, glab) == ("merged", "https://github.com/me/proj/pull/2")
    assert json.loads(log.read_text())[:5] == ["pr", "list", "--head", "friday/core", "--state"]


# ---------------------------------------------------------------- dash list
MR = {"iid": 7, "title": "t", "web_url": "https://gitlab.example.com/grp/proj/-/merge_requests/7",
      "source_branch": "friday/x", "draft": True, "author": {"username": "dev"}, "updated_at": "z"}


def gl_snap(node, origin, forge):
    s = snap(node)
    s["repos"].append({"path": "/r", "origin": origin, "forge": forge, "branch": "main", "goals": []})
    return s


def test_dash_lists_gitlab_mrs_via_glab(tmp_path):
    calls = []
    other = dict(MR, iid=8, source_branch="feature/y")
    d = make(tmp_path, Clock(), run=runner(json.dumps([MR, other]), calls=calls))
    d.store("alfred", gl_snap("alfred", GL_URL, "gitlab"))
    d.refresh_prs()
    assert len(calls) == 1 and calls[0][:5] == ["glab", "mr", "list", "-R", "gitlab.example.com/grp/proj"]
    (p,) = d.state()["prs"]
    assert p["number"] == 7 and p["url"] == MR["web_url"] and p["isDraft"] is True
    assert p["headRefName"] == "friday/x" and p["author"] == {"login": "dev"} and p["repo"] == "grp/proj"
    assert d.state()["prs_note"] is None


def test_dash_skips_forge_none_and_keeps_github_on_gh(tmp_path):
    calls = []
    d = make(tmp_path, Clock(), run=runner("[]", calls=calls))
    d.store("alfred", gl_snap("alfred", GL_URL, "none"))
    d.store("laptop", gl_snap("laptop", "git@github.com:me/proj.git", "github"))
    d.refresh_prs()
    assert len(calls) == 1 and calls[0][:5] == ["gh", "pr", "list", "-R", "me/proj"]


def test_dash_missing_glab_degrades_quietly(tmp_path):
    def missing(argv, **kw):
        raise FileNotFoundError(argv[0])
    d = make(tmp_path, Clock(), run=missing)
    d.store("alfred", gl_snap("alfred", GL_URL, "gitlab"))
    d.refresh_prs()
    s = d.state()
    assert s["prs"] == [] and "glab is not installed" in s["prs_note"]


def test_dash_glab_failure_degrades_quietly(tmp_path):
    d = make(tmp_path, Clock(), run=runner("", rc=1))
    d.store("alfred", gl_snap("alfred", GL_URL, "gitlab"))
    d.refresh_prs()
    assert d.state()["prs"] == [] and "glab failed" in d.state()["prs_note"]


# ---------------------------------------------------------------- the token: environment only
def dash_up(tmp_path, glab_signed_in):
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    log = tmp_path / "docker.log"
    script(bin_ / "docker", f"open({str(log)!r}, 'a').write(json.dumps({{'argv': argv, "
           "'gl': os.environ.get('GITLAB_TOKEN'), 'gh': os.environ.get('GH_TOKEN')}) + '\\n')\n")
    script(bin_ / "gh", "sys.exit(1)\n")
    script(bin_ / "glab", f"print({TOKEN!r})\n" if glab_signed_in else "sys.exit(1)\n")
    (tmp_path / "reg.toml").write_text("")
    env = {k: v for k, v in os.environ.items() if k not in ("GH_TOKEN", "GITLAB_TOKEN", "FRIDAY_NODES")}
    env.update(FRIDAY_NODES=str(tmp_path / "reg.toml"), HOME=str(tmp_path),
               PATH=f"{bin_}{os.pathsep}{private_bin(tmp_path / 'pybin')}")
    r = subprocess.run([sys.executable, str(FRIDAY), "dash", "up"], env=env, capture_output=True, text=True)
    return r, [json.loads(l) for l in log.read_text().splitlines()]


def test_dash_up_passes_gitlab_token_in_env_only(tmp_path):
    r, (c,) = dash_up(tmp_path, True)
    assert r.returncode == 0, r.stderr
    assert c["gl"] == TOKEN and TOKEN not in json.dumps(c["argv"])
    assert TOKEN not in r.stdout + r.stderr


def test_dash_up_glab_signed_out_leaves_token_unset(tmp_path):
    r, (c,) = dash_up(tmp_path, False)
    assert r.returncode == 0, r.stderr
    assert c["gl"] is None and "GITLAB_TOKEN left unset" in r.stdout
