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
