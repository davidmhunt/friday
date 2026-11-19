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
    fp = home / "f" / "bin" / "friday-python"  # the node's <plugin_dir>/bin/friday-python
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text('#!/bin/sh\nexec python3 "$@"\n')
    fp.chmod(0o755)
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


def _clean(tmp_path, repos, items, dry_run=False, sessions=()):
    """Run clean_script locally under a temp HOME with a fake tmux that tracks `sessions` (idle)."""
    home = tmp_path / "home"
    bin_ = home / ".local" / "bin"
    bin_.mkdir(parents=True, exist_ok=True)
    log = tmp_path / "tmux.log"
    fp = home / "f" / "bin" / "friday-python"
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text('#!/bin/sh\nexec python3 "$@"\n')
    fp.chmod(0o755)
    (bin_ / "tmux").write_text(
        "#!/bin/bash\nsub=$1; shift; t=; while [ $# -gt 0 ]; do [ \"$1\" = -t ] && t=$2; shift; done\n"
        f"t=${{t#=}}; t=${{t%:}}; echo \"$sub $t\" >> {log}\n"
        f"[ -f \"{tmp_path}/$t.pane\" ] || exit 1\n"
        f"[ \"$sub\" = capture-pane ] && cat \"{tmp_path}/$t.pane\"\n"
        f"[ \"$sub\" = kill-session ] && rm \"{tmp_path}/$t.pane\"\nexit 0\n")
    (bin_ / "tmux").chmod(0o755)
    for s in sessions:
        (tmp_path / f"friday-{s}.pane").write_text("done\n\n❯ \n")
    argv, stdin = ff.ssh_cmd(_node(repos), ff.clean_script(_node(repos), items, dry_run))
    r = subprocess.run(["bash", "-s"], input=stdin, capture_output=True, text=True,
                       env=dict(os.environ, HOME=str(home)))
    assert r.returncode == 0, r.stderr
    return r.stdout, log


def _trust(tmp_path, *paths):
    import json
    cfg = tmp_path / "home" / ".claude.json"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(json.dumps({"theme": "dark", "projects": {
        **{str(Path(p).resolve()): {"hasTrustDialogAccepted": True} for p in paths},
        "/other": {"x": 1}}}))
    return cfg


def _items(*wts):
    return [{"repo": "proj", "goal": w.name, "path": str(w)} for w in wts]


def test_clean_removes_worktree_branch_trust_and_idle_session(tmp_path):
    import json
    repos = tmp_path / "repos"
    c = _mkclone(repos, "proj", "git@github.com:me/proj.git")
    a, b = _wt(c, "a"), _wt(c, "b")
    cfg = _trust(tmp_path, a, b)
    out, log = _clean(tmp_path, repos, _items(a), sessions=["a"])
    assert "FRIDAY_CLEANED proj/a" in out
    assert not a.exists() and b.exists()
    br = subprocess.run(["git", "branch", "--list", "friday/*"], cwd=c, capture_output=True, text=True).stdout
    assert "friday/a" not in br and "friday/b" in br
    assert "worktree list" and str(a) not in subprocess.run(
        ["git", "worktree", "list"], cwd=c, capture_output=True, text=True).stdout
    data = json.loads(cfg.read_text())
    assert str(a.resolve()) not in data["projects"] and str(b.resolve()) in data["projects"]
    assert data["theme"] == "dark" and data["projects"]["/other"] == {"x": 1}
    assert "kill-session friday-a" in log.read_text()
    assert not list(cfg.parent.glob(".claude.json.friday-*"))


def test_clean_keeps_dirty_worktree_and_busy_session(tmp_path):
    repos = tmp_path / "repos"
    c = _mkclone(repos, "proj", "git@github.com:me/proj.git")
    d, busy = _wt(c, "d"), _wt(c, "busy")
    (d / "new.txt").write_text("x")
    cfg = _trust(tmp_path, d, busy)
    before = cfg.read_text()
    (tmp_path / "friday-busy.pane").write_text("esc to interrupt\n")
    out, log = _clean(tmp_path, repos, _items(d, busy))
    assert "FRIDAY_KEPT proj/d worktree remove refused" in out
    assert "FRIDAY_KEPT proj/busy session friday-busy is not idle" in out
    assert d.exists() and busy.exists() and cfg.read_text() == before
    assert "kill-session" not in log.read_text()
    br = subprocess.run(["git", "branch", "--list", "friday/*"], cwd=c, capture_output=True, text=True).stdout
    assert "friday/d" in br and "friday/busy" in br


def test_clean_dry_run_changes_nothing(tmp_path):
    repos = tmp_path / "repos"
    c = _mkclone(repos, "proj", "git@github.com:me/proj.git")
    a = _wt(c, "a")
    cfg = _trust(tmp_path, a)
    before = cfg.read_text()
    out, log = _clean(tmp_path, repos, _items(a), dry_run=True, sessions=["a"])
    assert "FRIDAY_WOULD proj/a: git worktree remove" in out and "kill-session" in out
    assert "FRIDAY_CLEANED" not in out
    assert a.exists() and cfg.read_text() == before and (tmp_path / "friday-a.pane").exists()
    assert "kill-session" not in log.read_text()
    assert "friday/a" in subprocess.run(["git", "branch"], cwd=c, capture_output=True, text=True).stdout


def test_run_clean_end_to_end_keeps_unmerged_reports_stray_deletes_nothing_else(tmp_path, monkeypatch):
    """Full flow through run_clean with a fake ssh (local bash under a temp HOME) and fake gh."""
    repos = tmp_path / "repos"
    c = _mkclone(repos, "proj", "git@github.com:me/proj.git")
    stray = _mkclone(repos, "odd", "git@github.com:me/other.git")
    merged, open_, dirty = _wt(c, "merged"), _wt(c, "open"), _wt(c, "dirty")
    (dirty / "x.txt").write_text("x")
    cfg = _trust(tmp_path, merged, open_, dirty)
    home = tmp_path / "home"
    fakebin = tmp_path / "fakebin"
    fakebin.mkdir()
    (fakebin / "gh").write_text("#!/bin/sh\nexit 0\n")  # only so shutil.which finds it; run is faked
    (fakebin / "gh").chmod(0o755)
    monkeypatch.setenv("PATH", f"{fakebin}{os.pathsep}{os.environ['PATH']}")
    gh = _Run(merged=["merged", "dirty"], on_origin=["open"])

    def run(cmd, **kw):
        if cmd[0] in ("gh", "git"):
            return gh(cmd, **kw)
        return subprocess.run(["bash", "-s"], input=kw["input"], capture_output=True, text=True,
                              env=dict(os.environ, HOME=str(home)))

    _inventory(tmp_path, repos)  # installs the fake tmux under the temp HOME
    # run_clean hands decide_clean no runner, so route its gh / ls-remote lookups to the fake.
    monkeypatch.setattr(ff, "pr_merged", lambda url, goal, run=None, _o=ff.pr_merged: _o(url, goal, gh))
    monkeypatch.setattr(ff, "branch_on_origin",
                        lambda url, goal, run=None, _o=ff.branch_on_origin: _o(url, goal, gh))
    res = ff.run_clean(_node(repos), URLS, run=run)
    assert res["error"] is None, res
    assert res["cleaned"] == ["proj/merged"], res
    assert any(k.startswith("proj/open:") for k in res["kept"])
    assert any(k.startswith("proj/dirty:") for k in res["kept"])
    assert [s["folder"] for s in res["strays"]] == ["odd"]
    assert not merged.exists() and open_.exists() and dirty.exists() and stray.exists() and c.exists()
    import json
    assert str(merged.resolve()) not in json.loads(cfg.read_text())["projects"]
