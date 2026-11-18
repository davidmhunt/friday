"""review-01: friday commits / finish use the directive's own change set."""
from test_friday import cli, repo, _g, fc  # noqa: F401


def _commit(repo, name, msg):
    (repo / name).write_text(name)
    _g(repo, "add", name)
    _g(repo, "commit", "-qm", msg)


def test_finish_log_lists_only_own_commits_and_start_prints_merge_base(repo):
    r = cli(repo, "start", "core-01")
    assert r.returncode == 0, r.stderr
    mb = _g(repo, "merge-base", "main", "HEAD").strip()
    assert f"base {mb}" in r.stdout and fc.read_marker(repo)["base"] == mb
    _commit(repo, "a.txt", "mine a\n\nDirective: core-01")
    _commit(repo, "o.txt", "other\n\nDirective: other-01")
    _commit(repo, "b.txt", "mine b\n\nDirective: core-01")
    assert cli(repo, "finish", "core-01").returncode == 0
    log = (repo / "docs/directives/core-01.md").read_text().split("## Log")[1]
    assert "mine a" in log and "mine b" in log and "other" not in log


def test_finish_base_override_lists_everything_since_sha(repo):
    cli(repo, "start", "core-01")
    base = _g(repo, "rev-parse", "HEAD").strip()
    _commit(repo, "o.txt", "other\n\nDirective: other-01")
    assert cli(repo, "finish", "core-01", "--base", base).returncode == 0
    assert "other" in (repo / "docs/directives/core-01.md").read_text().split("## Log")[1]


# ---------------------------------------------------------------- friday commits
import json  # noqa: E402


def _subjects(r):
    return [ln.split(" ", 1)[1] for ln in r.stdout.splitlines() if ln.count(" ") and not ln.startswith(("base", "untracked"))]


def _untracked(r):
    return [ln for ln in r.stdout.splitlines() if ln.startswith("untracked ")]


def test_commits_split_interleaved_directives(repo):
    cli(repo, "start", "core-01")
    _commit(repo, "a.txt", "mine a\n\nDirective: core-01")
    _commit(repo, "o.txt", "other\n\nDirective: other-01")
    _commit(repo, "b.txt", "mine b\n\nDirective: core-01")
    r = cli(repo, "commits", "core-01")
    assert r.returncode == 0, r.stderr
    assert r.stdout.startswith("base " + _g(repo, "merge-base", "main", "HEAD").strip())
    assert [s for s in _subjects(r)] == ["mine a", "mine b"] and not _untracked(r)
    j = json.loads(cli(repo, "commits", "core-01", "--json").stdout)
    assert [c["subject"] for c in j["commits"]] == ["mine a", "mine b"] and j["untracked"] == []


def test_plan_only_commit_without_trailer_is_neither_listed_nor_untracked(repo):
    cli(repo, "start", "core-01")
    _commit(repo, "a.txt", "mine a\n\nDirective: core-01")
    g = repo / "docs/goals/core.md"
    g.write_text(g.read_text() + "\namended\n")
    _g(repo, "add", "docs/goals/core.md")
    _g(repo, "commit", "-qm", "amend plan")
    r = cli(repo, "commits", "core-01")
    assert r.returncode == 0 and _subjects(r) == ["mine a"] and not _untracked(r)


def test_untagged_code_commit_is_untracked(repo):
    cli(repo, "start", "core-01")
    _commit(repo, "a.txt", "mine a\n\nDirective: core-01")
    _commit(repo, "oops.txt", "forgot the trailer")
    r = cli(repo, "commits", "core-01")
    assert r.returncode == 0 and _subjects(r) == ["mine a"]
    assert len(_untracked(r)) == 1 and "forgot the trailer" in _untracked(r)[0]


def test_blocked_unblock_then_more_commits_keep_earlier_ones(repo):
    cli(repo, "start", "core-01")
    _commit(repo, "a.txt", "mine a\n\nDirective: core-01")
    assert cli(repo, "finish", "core-01", "--blocked", "needs a board").returncode == 0
    p = repo / "docs/directives/core-01.md"
    p.write_text(p.read_text().replace("Status: blocked: needs a board", "Status: approved"))
    _g(repo, "add", "-A")
    _g(repo, "commit", "-qm", "core-01: unblock\n\nDirective: core-01")
    assert cli(repo, "start", "core-01").returncode == 0
    _commit(repo, "b.txt", "mine b\n\nDirective: core-01")
    r = cli(repo, "commits", "core-01")
    assert r.returncode == 0, r.stderr
    assert _subjects(r) == ["mine a", "mine b"] and not _untracked(r)


def test_merging_base_into_goal_branch_keeps_commits_and_adds_no_untracked(repo):
    cli(repo, "start", "core-01")
    _commit(repo, "a.txt", "mine a\n\nDirective: core-01")
    _g(repo, "checkout", "-q", "main")
    _commit(repo, "m.txt", "main moved")
    _g(repo, "checkout", "-q", "friday/core-01")
    _commit(repo, "b.txt", "mine b\n\nDirective: core-01")
    _g(repo, "merge", "-q", "--no-edit", "main")
    r = cli(repo, "commits", "core-01")
    assert r.returncode == 0, r.stderr
    assert _subjects(r) == ["mine a", "mine b"] and not _untracked(r)
    assert r.stdout.startswith("base " + _g(repo, "rev-parse", "main").strip())


def test_finish_log_excludes_other_directives_and_untagged_plan_commits(repo):
    cli(repo, "start", "core-01")
    _commit(repo, "a.txt", "mine a\n\nDirective: core-01")
    _commit(repo, "o.txt", "other\n\nDirective: other-01")
    g = repo / "docs/goals/core.md"
    g.write_text(g.read_text() + "\namended\n")
    _g(repo, "add", "docs/goals/core.md")
    _g(repo, "commit", "-qm", "amend plan")
    assert cli(repo, "finish", "core-01").returncode == 0
    log = (repo / "docs/directives/core-01.md").read_text().split("## Log")[1]
    assert "mine a" in log and "other" not in log and "amend plan" not in log


def test_commits_exit_codes(repo):
    cli(repo, "start", "core-01")
    assert cli(repo, "commits", "core-01").returncode == 3
    _commit(repo, "a.txt", "mine a\n\nDirective: core-01")
    assert cli(repo, "commits", "core-01").returncode == 0
    r = cli(repo, "commits", "no-such-01")
    assert r.returncode == 2 and r.stderr.strip()


def test_no_prompt_mentions_review_base():
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    for f in ("workflows/execute.js", "agents/verifier.md", "skills/directive/SKILL.md"):
        t = (root / f).read_text()
        assert "reviewBase" not in t and "review_base" not in t, f
