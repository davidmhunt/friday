"""review-01: friday commits / finish use the directive's own change set."""
from test_friday import cli, repo, _g, fc  # noqa: F401


def _commit(repo, name, msg):
    (repo / name).write_text(name)
    _g(repo, "add", name)
    _g(repo, "commit", "--no-verify", "-qm", msg)


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
    return [ln.split(" ", 1)[1] for ln in r.stdout.splitlines() if ln.count(" ") and not ln.startswith(("base", "untracked", "plan "))]


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
    _g(repo, "commit", "--no-verify", "-qm", "amend plan")
    r = cli(repo, "commits", "core-01")
    assert r.returncode == 0 and _subjects(r) == ["mine a"] and not _untracked(r)


def test_plan_commit_with_settings_json_is_plan_only(repo):
    _g(repo, "checkout", "-qb", "friday/core")
    (repo / ".claude").mkdir(exist_ok=True)
    (repo / ".claude/settings.json").write_text("{}\n")
    g = repo / "docs/goals/core.md"
    g.write_text(g.read_text() + "\nplanned\n")
    _g(repo, "add", ".claude/settings.json", "docs/goals/core.md")
    _g(repo, "commit", "--no-verify", "-qm", "plan: core\n\nDirective: core-01")
    cli(repo, "start", "core-01")
    _commit(repo, "a.txt", "mine a\n\nDirective: core-01")
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
    _g(repo, "commit", "--no-verify", "-qm", "core-01: unblock\n\nDirective: core-01")
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
    _g(repo, "merge", "--no-verify", "-q", "--no-edit", "main")
    r = cli(repo, "commits", "core-01")
    assert r.returncode == 0, r.stderr
    assert _subjects(r) == ["mine a", "mine b"] and not _untracked(r)
    assert r.stdout.startswith("base " + _g(repo, "rev-parse", "main").strip())


def test_teammate_commit_merged_by_start_is_not_untracked(repo, tmp_path):
    import subprocess
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    _g(repo, "remote", "add", "origin", str(origin))
    _g(repo, "push", "-q", "origin", "main")
    # a teammate pushes to origin/main after the plan commit
    mate = tmp_path / "mate"
    subprocess.run(["git", "clone", "-q", str(origin), str(mate)], check=True)
    for k, v in (("user.name", "m"), ("user.email", "m@t")):
        subprocess.run(["git", "-C", str(mate), "config", k, v], check=True)
    (mate / "t.txt").write_text("t")
    subprocess.run(["git", "-C", str(mate), "add", "t.txt"], check=True)
    subprocess.run(["git", "-C", str(mate), "commit", "--no-verify", "-qm", "teammate work"], check=True)
    subprocess.run(["git", "-C", str(mate), "push", "-q", "origin", "main"], check=True)
    r = cli(repo, "start", "core-01")
    assert r.returncode == 0, r.stderr
    assert (repo / "t.txt").exists()  # start merged it
    _commit(repo, "a.txt", "mine a\n\nDirective: core-01")
    r = cli(repo, "commits", "core-01")
    assert r.returncode == 0, r.stderr
    assert _subjects(r) == ["mine a"] and not _untracked(r)
    assert "teammate work" not in r.stdout
    _commit(repo, "oops.txt", "forgot the trailer")
    r = cli(repo, "commits", "core-01")
    assert len(_untracked(r)) == 1 and "forgot the trailer" in _untracked(r)[0]


def test_merging_unrelated_branch_still_surfaces_its_commits(repo):
    cli(repo, "start", "core-01")
    _commit(repo, "a.txt", "mine a\n\nDirective: core-01")
    _g(repo, "checkout", "-q", "-b", "side", "main")
    _commit(repo, "s.txt", "side work")
    _g(repo, "checkout", "-q", "friday/core-01")
    _g(repo, "merge", "--no-verify", "-q", "--no-ff", "-m", "merge side", "side")
    r = cli(repo, "commits", "core-01")
    assert r.returncode == 0, r.stderr
    assert any("side work" in ln for ln in _untracked(r))


def test_finish_log_excludes_other_directives_and_untagged_plan_commits(repo):
    cli(repo, "start", "core-01")
    _commit(repo, "a.txt", "mine a\n\nDirective: core-01")
    _commit(repo, "o.txt", "other\n\nDirective: other-01")
    g = repo / "docs/goals/core.md"
    g.write_text(g.read_text() + "\namended\n")
    _g(repo, "add", "docs/goals/core.md")
    _g(repo, "commit", "--no-verify", "-qm", "amend plan")
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


def test_plan_commit_on_goal_branch_with_trailer_is_not_own_work(repo):
    cli(repo, "start", "core-01")
    g = repo / "docs/goals/core.md"
    g.write_text(g.read_text() + "\n")
    _g(repo, "add", "docs/goals/core.md")
    _g(repo, "commit", "--no-verify", "-qm", "plan: core\n\nDirective: core-01\nDirective: core-02")
    _commit(repo, "a.txt", "work\n\nDirective: core-01")
    r = cli(repo, "commits", "core-01")
    assert r.returncode == 0, r.stderr
    assert _subjects(r) == ["work"] and not _untracked(r)


# ---------------------------------------------------------------- plan edits after start (tt-10)

def _plan_edit(repo, msg):
    p = repo / "docs/directives/core-01.md"
    p.write_text(p.read_text() + "\nedit\n")
    _g(repo, "add", "docs/directives/core-01.md")
    _g(repo, "commit", "--no-verify", "-qm", msg)


def _plan_lines(r):
    return [ln for ln in r.stdout.splitlines() if ln.startswith("plan ")]


def test_plan_commit_before_start_is_excluded_not_a_plan_line(repo):
    _g(repo, "checkout", "-qb", "friday/core")
    (repo / ".claude").mkdir(exist_ok=True)
    (repo / ".claude/settings.json").write_text("{}\n")
    g = repo / "docs/goals/core.md"
    g.write_text(g.read_text() + "\nplanned\n")
    _g(repo, "add", ".claude/settings.json", "docs/goals/core.md")
    _g(repo, "commit", "--no-verify", "-qm", "plan: core\n\nDirective: core-01\nDirective: core-02")
    cli(repo, "start", "core-01")
    assert (repo / "runs/core-01/start").read_text().strip() == _g(repo, "rev-parse", "HEAD").strip()
    _commit(repo, "a.txt", "mine a\n\nDirective: core-01")
    r = cli(repo, "commits", "core-01")
    assert r.returncode == 0 and _subjects(r) == ["mine a"]
    assert not _untracked(r) and not _plan_lines(r)
    assert json.loads(cli(repo, "commits", "core-01", "--json").stdout)["plan"] == []


def test_trailered_and_untrailered_plan_edits_after_start_are_plan_lines(repo):
    cli(repo, "start", "core-01")
    _commit(repo, "a.txt", "mine a\n\nDirective: core-01")
    _plan_edit(repo, "rewrite verify\n\nDirective: core-01")
    _plan_edit(repo, "rewrite steps")
    r = cli(repo, "commits", "core-01")
    assert r.returncode == 0 and _subjects(r) == ["mine a"] and not _untracked(r)
    assert [ln.split(" ", 2)[2] for ln in _plan_lines(r)] == ["rewrite verify", "rewrite steps"]
    j = json.loads(cli(repo, "commits", "core-01", "--json").stdout)
    assert [p["subject"] for p in j["plan"]] == ["rewrite verify", "rewrite steps"]
    assert [c["subject"] for c in j["commits"]] == ["mine a"]


def test_restart_keeps_first_start_point(repo):
    cli(repo, "start", "core-01")
    first = (repo / "runs/core-01/start").read_text()
    _commit(repo, "a.txt", "mine a\n\nDirective: core-01")
    _plan_edit(repo, "rewrite verify")
    assert cli(repo, "start", "core-01").returncode == 0
    assert (repo / "runs/core-01/start").read_text() == first
    assert len(_plan_lines(cli(repo, "commits", "core-01"))) == 1


def test_absent_start_file_excludes_all_plan_only_commits(repo):
    cli(repo, "start", "core-01")
    _commit(repo, "a.txt", "mine a\n\nDirective: core-01")
    _plan_edit(repo, "rewrite verify\n\nDirective: core-01")
    (repo / "runs/core-01/start").unlink()
    r = cli(repo, "commits", "core-01")
    assert r.returncode == 0 and _subjects(r) == ["mine a"]
    assert not _plan_lines(r) and not _untracked(r)


def test_code_commit_with_trailer_after_start_is_own_work_not_plan(repo):
    cli(repo, "start", "core-01")
    _commit(repo, "a.txt", "mine a\n\nDirective: core-01")
    r = cli(repo, "commits", "core-01")
    assert _subjects(r) == ["mine a"] and not _plan_lines(r)


# ---------------------------------------------------------------- cm-01 (#30)
def _a_merges_side(repo, trailer="other-01"):
    """Directive `other-01` merges an untrailered side branch and hand-commits; core-01 starts after."""
    _g(repo, "checkout", "-q", "-b", "side", "main")
    _commit(repo, "s1.txt", "side one")
    _commit(repo, "s2.txt", "side two")
    _g(repo, "checkout", "-q", "friday/core-01")
    _g(repo, "merge", "--no-verify", "-q", "--no-ff", "-m", f"merge side\n\nDirective: {trailer}", "side")
    _commit(repo, "hand.txt", "hand fix")


def test_side_merge_by_earlier_directive_is_not_untracked_for_later_one(repo):
    _a_merges_side(repo)
    assert cli(repo, "start", "core-01").returncode == 0
    _commit(repo, "b.txt", "mine b\n\nDirective: core-01")
    r = cli(repo, "commits", "core-01")
    assert r.returncode == 0, r.stderr
    assert _subjects(r) == ["mine b"] and not _untracked(r), r.stdout


def test_side_merge_by_earlier_directive_excluded_without_start_file(repo):
    _a_merges_side(repo)
    cli(repo, "start", "core-01")
    _commit(repo, "b.txt", "mine b\n\nDirective: core-01")
    (repo / "runs/core-01/start").unlink()
    r = cli(repo, "commits", "core-01")
    assert r.returncode == 0, r.stderr
    assert "side one" not in r.stdout and "side two" not in r.stdout
    assert "mine b" in r.stdout


def test_untrailered_commit_after_start_is_still_untracked(repo):
    _a_merges_side(repo)
    cli(repo, "start", "core-01")
    _commit(repo, "b.txt", "mine b\n\nDirective: core-01")
    _commit(repo, "late.txt", "late untrailered")
    r = cli(repo, "commits", "core-01")
    assert _subjects(r) == ["mine b"]
    assert len(_untracked(r)) == 1 and "late untrailered" in _untracked(r)[0]


def test_side_merge_trailed_with_own_id_lists_side_commits(repo):
    cli(repo, "start", "core-01")
    _a_merges_side(repo, trailer="core-01")
    r = cli(repo, "commits", "core-01")
    assert any("side one" in ln for ln in _untracked(r)), r.stdout
    assert any("side two" in ln for ln in _untracked(r)), r.stdout
