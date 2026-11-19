"""tt-05: friday start finds a directive that exists only on Base, merges Base, and starts it."""
from test_friday import cli, repo, remote_repo, _g, DIRECTIVE, GOAL, fc  # noqa: F401


def _amend_main(repo):
    _g(repo, "switch", "-q", "main")
    (repo / "docs/directives/core-02.md").write_text(
        DIRECTIVE.replace("core-01", "core-02").replace("Land: pr", "Land: goal"))
    (repo / "docs/goals/core.md").write_text(GOAL.replace("1. core-01: Make the thing",
                                             "1. core-02: Make the thing\n2. core-01: Make the thing"))
    _g(repo, "add", ".")
    _g(repo, "commit", "--no-verify", "-qm", "plan core-02")
    _g(repo, "switch", "-q", "friday/core-01")


def test_start_finds_directive_on_base(repo):
    _amend_main(repo)
    assert not (repo / "docs/directives/core-02.md").exists()
    r = cli(repo, "start", "core-02")
    assert r.returncode == 0, r.stderr
    assert "found core-02 on main: merging main into friday/core" in r.stdout
    assert _g(repo, "branch", "--show-current").strip() == "friday/core"
    assert (repo / "docs/directives/core-02.md").exists()
    assert fc.read_marker(repo)["id"] == "core-02"


def test_start_not_found_names_where_it_looked(repo):
    r = cli(repo, "start", "core-09")
    assert r.returncode != 0
    assert "core-09.md" in r.stderr and "main" in r.stderr


def _edit(repo, branch, rel, fn, msg):
    _g(repo, "switch", "-q", branch)
    p = repo / rel
    p.write_text(fn(p.read_text()))
    _g(repo, "add", ".")
    _g(repo, "commit", "--no-verify", "-qm", msg)


def _goal_branch(repo):
    _g(repo, "switch", "-q", "-c", "friday/core", "main")


def test_status_only_conflict_keeps_goal_branch(repo):
    _goal_branch(repo)
    _amend_main(repo)
    _edit(repo, "main", "docs/goals/core.md", lambda t: t.replace("Status: approved", "Status: blocked: x"), "m")
    _edit(repo, "friday/core", "docs/goals/core.md", lambda t: t.replace("Status: approved", "Status: running"), "g")
    r = cli(repo, "start", "core-02")
    assert r.returncode == 0, r.stderr
    goal = (repo / "docs/goals/core.md").read_text()
    assert "Status: running" in goal and "<<<<" not in goal
    assert "1. core-02:" in goal  # the body comes from Base


def test_step_conflict_aborts_and_names_file(repo):
    _goal_branch(repo)
    _amend_main(repo)
    _edit(repo, "main", "docs/goals/core.md", lambda t: t.replace("Do the core.", "Base text."), "m")
    _edit(repo, "friday/core", "docs/goals/core.md", lambda t: t.replace("Do the core.", "Branch text."), "g")
    r = cli(repo, "start", "core-02")
    assert r.returncode != 0
    assert "docs/goals/core.md" in r.stderr
    assert _g(repo, "status", "--porcelain", "--untracked-files=no").strip() == ""


def test_done_goal_with_new_directive_becomes_running(repo):
    _goal_branch(repo)
    _amend_main(repo)
    _edit(repo, "friday/core", "docs/goals/core.md", lambda t: t.replace("Status: approved", "Status: done"), "g")
    _edit(repo, "friday/core", "docs/directives/core-01.md",
          lambda t: t.replace("Status: approved", "Status: done"), "g2")
    r = cli(repo, "start", "core-02")
    assert r.returncode == 0, r.stderr
    assert "Status: running" in (repo / "docs/goals/core.md").read_text()


def test_start_finds_directive_on_origin_base(remote_repo):
    repo, _origin = remote_repo
    _amend_main(repo)
    _g(repo, "push", "-q", "origin", "main")
    _g(repo, "reset", "-q", "--hard", "HEAD")  # keep branch friday/core-01 without the amendment
    r = cli(repo, "start", "core-02")
    assert r.returncode == 0, r.stderr
    assert "found core-02 on" in r.stdout and "merging main into friday/core" in r.stdout
    assert (repo / "docs/directives/core-02.md").exists()
