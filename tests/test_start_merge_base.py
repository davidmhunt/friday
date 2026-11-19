"""tt-05: friday start finds a directive that exists only on Base, merges Base, and starts it."""
from test_friday import cli, repo, _g, DIRECTIVE, GOAL, fc  # noqa: F401


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
