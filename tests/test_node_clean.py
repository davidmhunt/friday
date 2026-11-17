"""Node clean: inventory script run locally through ssh_cmd's stdin under a temp HOME, fake tmux."""
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
import friday_fleet as ff  # noqa: E402

GIT = ["git", "-c", "user.name=t", "-c", "user.email=t@t"]


def _g(cwd, *a):
    subprocess.run([*GIT, *a], cwd=cwd, check=True, capture_output=True)


def _node(repos):
    return ff.Node("w", "worker", "me@w", repos=str(repos), plugin_dir="~/f")


def _mkclone(repos, folder, url):
    c = repos / folder
    c.mkdir(parents=True)
    _g(c, "init", "-q", "-b", "main")
    _g(c, "remote", "add", "origin", url)
    (c / "a.txt").write_text("a")
    _g(c, "add", ".")
    _g(c, "commit", "-qm", "init")
    return c


def _wt(clone, goal):
    wt = clone.parent / f"{clone.name}.friday" / goal
    _g(clone, "worktree", "add", "-q", "-b", f"friday/{goal}", str(wt))
    return wt


def _inventory(tmp_path, repos, panes=None):
    home = tmp_path / "home"
    bin_ = home / ".local" / "bin"
    bin_.mkdir(parents=True, exist_ok=True)
    panes = panes or {}
    tmux = ["#!/bin/bash", 'sub=$1; shift; t=; while [ $# -gt 0 ]; do [ "$1" = -t ] && t=$2; shift; done',
            't=${t#=}; t=${t%:}']
    for name, text in panes.items():
        (tmp_path / f"{name}.pane").write_text(text)
    tmux += ['f="' + str(tmp_path) + '/${t}.pane"', '[ -f "$f" ] || exit 1',
             '[ "$sub" = capture-pane ] && cat "$f"', "exit 0"]
    (bin_ / "tmux").write_text("\n".join(tmux) + "\n")
    (bin_ / "tmux").chmod(0o755)
    argv, stdin = ff.ssh_cmd(_node(repos), ff.inventory_script(_node(repos)))
    r = subprocess.run(["bash", "-s"], input=stdin, capture_output=True, text=True,
                       env=dict(os.environ, HOME=str(home)))
    assert r.returncode == 0, r.stderr
    return ff.parse_inventory(r.stdout)


def test_inventory_worktrees_and_strays(tmp_path):
    repos = tmp_path / "repos"
    c = _mkclone(repos, "proj", "git@github.com:me/proj.git")
    clean, dirty, untr, busy, ign = (_wt(c, g) for g in ("clean", "dirty", "untr", "busy", "ign"))
    (dirty / "a.txt").write_text("changed")
    (untr / "new.txt").write_text("x")
    (ign / "runs").mkdir()
    (ign / "runs" / "n.md").write_text("x")
    (clean / "docs" / "goals").mkdir(parents=True)
    (clean / "docs" / "goals" / "clean.md").write_text("# g\nStatus: done\n")
    _g(clean, "add", ".")
    _g(clean, "commit", "-qm", "goal")
    _mkclone(repos, "oddname", "https://github.com/me/other-repo")
    _mkclone(repos, "proj2", "https://github.com/me/proj2/")
    inv = _inventory(tmp_path, repos, {
        "friday-busy": "some output\nesc to interrupt\n",
        "friday-clean": "done\n\n❯ \n"})
    by = {w["goal"]: w for w in inv["worktrees"]}
    assert set(by) == {"clean", "dirty", "untr", "busy", "ign"}
    w = by["clean"]
    assert (w["repo"], w["branch"], w["goalstatus"]) == ("proj", "friday/clean", "done")
    assert len(w["head"]) >= 7 and w["path"].endswith("proj.friday/clean")
    assert not w["tracked"] and not w["untracked"]
    assert w["session"] is True and w["idle"] is True
    assert by["dirty"]["tracked"] and not by["dirty"]["untracked"]
    assert by["untr"]["untracked"] and not by["untr"]["tracked"]
    assert not by["ign"]["tracked"] and not by["ign"]["untracked"]
    assert by["busy"]["session"] is True and by["busy"]["idle"] is False
    assert by["dirty"]["session"] is False and by["dirty"]["idle"] is None
    assert by["dirty"]["goalstatus"] == "-"
    assert [(s["folder"], s["origin"]) for s in inv["stray"]] == [("oddname", "other-repo")]


def test_inventory_missing_repos(tmp_path):
    assert _inventory(tmp_path, tmp_path / "nope") == {"worktrees": [], "stray": []}


def _wt_rec(goal, **kw):
    return {"repo": "proj", "goal": goal, "branch": f"friday/{goal}", "head": "abc", "tracked": False,
            "untracked": False, "session": False, "idle": None, "goalstatus": "-",
            "path": f"/r/proj.friday/{goal}", **kw}


class _Run:
    """Fake gh and git ls-remote. merged: goals with a merged PR; on_origin: goals still on origin."""
    def __init__(self, merged=(), on_origin=(), gh_fails=False):
        self.merged, self.on_origin, self.gh_fails = set(merged), set(on_origin), gh_fails

    def __call__(self, cmd, **kw):
        out = ""
        rc = 0
        if cmd[0] == "gh":
            goal = cmd[cmd.index("--head") + 1].split("/", 1)[1]
            assert "--state" in cmd and cmd[cmd.index("--state") + 1] == "merged"
            out, rc = ('[{"number": 1}]' if goal in self.merged else "[]"), (1 if self.gh_fails else 0)
        else:
            goal = cmd[-1].split("/", 1)[1]
            out = f"deadbeef\trefs/heads/friday/{goal}\n" if goal in self.on_origin else ""
        return subprocess.CompletedProcess(cmd, rc, out, "")


URLS = {"proj": "git@github.com:me/proj.git"}


def _decide(wts, run, have_gh=True):
    return ff.decide_clean({"worktrees": wts, "stray": []}, URLS, run, have_gh)


def test_decide_merged_pr_removes_even_if_branch_on_origin():
    d = _decide([_wt_rec("m", session=True, idle=True)], _Run(merged={"m"}, on_origin={"m"}))
    assert [w["goal"] for w in d["remove"]] == ["m"] and d["remove"][0]["why"] == "PR merged"
    assert d["keep"] == []


def test_decide_keeps_with_reasons():
    wts = [_wt_rec("open"), _wt_rec("dirty", tracked=True), _wt_rec("untr", untracked=True),
           _wt_rec("busy", session=True, idle=False), _wt_rec("notdone", goalstatus="approved")]
    d = _decide(wts, _Run(merged={"dirty", "untr", "busy"}, on_origin={"open"}))
    assert d["remove"] == []
    why = {w["goal"]: r for w, r in d["keep"]}
    assert set(why) == {"open", "dirty", "untr", "busy", "notdone"}
    assert "unfinished" in why["open"] and "tracked" in why["dirty"] and "untracked" in why["untr"]
    assert "not idle" in why["busy"] and "not done" in why["notdone"]
    assert all("\n" not in r for r in why.values())


def test_decide_branch_gone_fallback_without_gh():
    wts = [_wt_rec("gone", goalstatus="done"), _wt_rec("gonenotdone", goalstatus="approved"),
           _wt_rec("there", goalstatus="done")]
    d = _decide(wts, _Run(merged={"gone", "there"}, on_origin={"there"}), have_gh=False)
    assert [w["goal"] for w in d["remove"]] == ["gone"]
    assert {w["goal"] for w, _ in d["keep"]} == {"gonenotdone", "there"}
    assert any("gh not available" in n for n in d["notes"])


def test_decide_squash_merged_branch_still_on_origin_detected_via_gh():
    d = _decide([_wt_rec("sq", goalstatus="approved")], _Run(merged={"sq"}, on_origin={"sq"}))
    assert [w["goal"] for w in d["remove"]] == ["sq"]


def test_decide_gh_failure_falls_back_with_note():
    d = _decide([_wt_rec("g", goalstatus="done")], _Run(gh_fails=True))
    assert [w["goal"] for w in d["remove"]] == ["g"]
    assert any("gh failed" in n for n in d["notes"])
