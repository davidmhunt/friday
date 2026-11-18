"""review-02: friday start merges the goal's Base into the goal branch."""
import subprocess
from test_friday import cli, repo, _g, fc  # noqa: F401


def _commit_on(repo, branch, name, text, msg):
    _g(repo, "switch", "-q", branch)
    (repo / name).write_text(text)
    _g(repo, "add", name)
    _g(repo, "commit", "-qm", msg)


def test_start_merges_base_with_trailer(repo):
    _commit_on(repo, "friday/core-01", "own.txt", "own", "own work")
    _commit_on(repo, "main", "plan.txt", "amend", "amend plan")
    _g(repo, "switch", "-q", "friday/core-01")
    head = _g(repo, "rev-parse", "HEAD").strip()
    r = cli(repo, "start", "core-01")
    assert r.returncode == 0, r.stderr
    sha = _g(repo, "rev-parse", "--short", "HEAD").strip()
    assert f"merged main {sha}" in r.stdout
    assert (repo / "plan.txt").exists()
    msg = _g(repo, "log", "-1", "--format=%B")
    assert msg.startswith("Merge main into friday/core-01 before core-01") and "Directive: core-01" in msg
    assert _g(repo, "rev-parse", "HEAD^1").strip() == head
    # already up to date: no second merge
    r = cli(repo, "start", "core-01")
    assert r.returncode == 0 and "merged" not in r.stdout


def test_start_conflict_aborts_and_changes_nothing(repo):
    _commit_on(repo, "friday/core-01", "c.txt", "branch", "branch c")
    _commit_on(repo, "main", "c.txt", "base", "base c")
    _g(repo, "switch", "-q", "friday/core-01")
    head = _g(repo, "rev-parse", "HEAD").strip()
    r = cli(repo, "start", "core-01")
    assert r.returncode != 0 and "c.txt" in r.stderr
    assert _g(repo, "rev-parse", "HEAD").strip() == head
    assert _g(repo, "status", "--porcelain", "--untracked-files=no") == ""
    assert not (repo / ".git" / "MERGE_HEAD").exists() and fc.read_marker(repo) is None
    assert (repo / "c.txt").read_text() == "branch"


def test_start_dirty_tree_refuses(repo):
    _commit_on(repo, "main", "plan.txt", "amend", "amend plan")
    _g(repo, "switch", "-q", "friday/core-01")
    (repo / ".claude/friday.json").write_text("{}")
    r = cli(repo, "start", "core-01")
    assert r.returncode != 0 and "uncommitted" in r.stderr


def test_failed_fetch_falls_back_to_local_base(repo, tmp_path):
    _g(repo, "remote", "add", "origin", str(tmp_path / "nowhere"))
    _commit_on(repo, "main", "plan.txt", "amend", "amend plan")
    _g(repo, "switch", "-q", "friday/core-01")
    r = cli(repo, "start", "core-01")
    assert r.returncode == 0, r.stderr
    assert "warning" in r.stderr and "merged main" in r.stdout and (repo / "plan.txt").exists()


# ---------------------------------------------------------------- commit-msg guard
def _commit(repo, msg, name="f.txt", *flags):
    (repo / name).write_text(msg)
    _g(repo, "add", name)
    return subprocess.run(["git", "-C", str(repo), "commit", "-q", *flags, "-m", msg],
                          capture_output=True, text=True)


def _hook(repo):
    return repo / ".git" / "hooks" / "commit-msg"


def test_hook_refuses_without_trailer_allows_with(repo):
    assert cli(repo, "start", "core-01").returncode == 0
    r = _commit(repo, "no trailer")
    assert r.returncode != 0 and "Directive: core-01" in r.stderr and "--no-verify" in r.stderr
    assert _commit(repo, "ok\n\nDirective: core-01").returncode == 0
    assert _commit(repo, "forced", "g.txt", "--no-verify").returncode == 0


def test_hook_allows_without_marker(repo):
    assert cli(repo, "init").returncode == 0 and _hook(repo).exists()
    assert _commit(repo, "anything").returncode == 0


def test_existing_hook_preserved_and_runs(repo):
    h = _hook(repo)
    h.parent.mkdir(exist_ok=True)
    h.write_text("#!/bin/sh\ngrep -q nope \"$1\" && exit 7\nexit 0\n")
    h.chmod(0o755)
    assert cli(repo, "init").returncode == 0
    assert (h.parent / "commit-msg.local").read_text().startswith("#!/bin/sh\ngrep")
    r = _commit(repo, "nope")
    assert r.returncode != 0
    assert _commit(repo, "fine").returncode == 0
    cli(repo, "start", "core-01")
    assert _commit(repo, "nope\n\nDirective: core-01", "h.txt").returncode != 0


def test_install_twice_and_uninstall_restores(repo):
    h = _hook(repo)
    h.parent.mkdir(exist_ok=True)
    h.write_text("#!/bin/sh\nexit 0\n")
    h.chmod(0o755)
    cli(repo, "init")
    cli(repo, "init")
    cli(repo, "start", "core-01")
    assert sorted(p.name for p in h.parent.glob("commit-msg*") if p.suffix != ".sample") == ["commit-msg", "commit-msg.local"]
    assert (h.parent / "commit-msg.local").read_text() == "#!/bin/sh\nexit 0\n"
    r = cli(repo, "uninstall", "--bin-dir", str(repo / "nobin"))
    assert r.returncode == 0, r.stderr
    assert h.read_text() == "#!/bin/sh\nexit 0\n" and not (h.parent / "commit-msg.local").exists()


def test_uninstall_without_local_removes_hook(repo):
    cli(repo, "init")
    cli(repo, "uninstall", "--bin-dir", str(repo / "nobin"))
    assert not _hook(repo).exists()


def test_hooks_path_honoured(repo, tmp_path):
    _g(repo, "config", "core.hooksPath", str(tmp_path / "hp"))
    cli(repo, "init")
    assert (tmp_path / "hp" / "commit-msg").exists() and not _hook(repo).exists()


def test_record_only_commit_naming_goal_sibling_passes(repo):
    assert cli(repo, "start", "core-01").returncode == 0
    d = repo / "docs" / "directives"
    goal = fc.parse_directive_full((d / "core-01.md").read_text())["goal"]
    assert goal
    (d / "core-02.md").write_text((d / "core-01.md").read_text().replace("core-01", "core-02"))
    _g(repo, "add", "docs/directives/core-02.md")
    ok = subprocess.run(["git", "-C", str(repo), "commit", "-qm", "record\n\nDirective: core-02"],
                        capture_output=True, text=True)
    assert ok.returncode == 0, ok.stderr
    # a code file in the commit is not a record-only commit
    (repo / "x.py").write_text("x")
    _g(repo, "add", "x.py")
    bad = subprocess.run(["git", "-C", str(repo), "commit", "-qm", "code\n\nDirective: core-02"],
                         capture_output=True, text=True)
    assert bad.returncode != 0


# ---------------------------------------------------------------- PreToolUse guard
def test_pretool_judges_the_repo_the_command_commits_in(repo, tmp_path):
    from test_friday import pre
    assert cli(repo, "start", "core-01").returncode == 0
    other = tmp_path / "wt"
    _g(repo, "worktree", "add", "-q", str(other), "main")
    # the session's cwd is on the directive branch: free, and no trailer check (the git hook does that)
    assert pre(repo, "git commit -m x")[0] is None
    # a commit in the other worktree (on main, no marker) is judged by that worktree
    assert pre(repo, f"git -C {other} commit -m x")[0] == "ask"
    assert pre(repo, f"cd {other} && git commit -m x")[0] == "ask"
    # and with a marker there, the same commit is denied
    fc.write_marker(other, {"id": "core-01"})
    assert pre(repo, f"git -C {other} commit -m x")[0] == "deny"
    # the other way round: session in the main worktree, command commits in the directive worktree
    assert pre(other, f"git -C {repo} commit -m x")[0] is None
