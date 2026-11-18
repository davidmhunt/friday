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
