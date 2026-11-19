"""finish keeps notes from breaking the Log (#14)."""
import subprocess

import pytest

from test_friday import repo, cli  # noqa: F401

NOTES = """# A
- plain bullet
## Step 1: x
### B
```
## not a heading
# nor this
```
#### D
"""


def _run(repo, *finish_args):
    (repo / "runs" / "core-01").mkdir(parents=True)
    (repo / "runs" / "core-01" / "notes.md").write_text(NOTES)
    r = cli(repo, "start", "core-01")
    assert r.returncode == 0, r.stderr
    r = cli(repo, "finish", "core-01", *finish_args)
    assert r.returncode == 0, r.stderr
    log = (repo / "docs" / "directives" / "core-01.md").read_text().split("\n## Log", 1)[1]
    return log


@pytest.mark.parametrize("args", [(), ("--blocked", "needs a board")])
def test_headed_notes_keep_directive_valid(repo, args):
    log = _run(repo, *args)
    lines = log.split("\n")
    assert "#### A" in lines and "#### Step 1: x" in lines and "#### B" in lines
    assert "#### D" in lines
    assert "# A" not in lines and "## Step 1: x" not in lines and "### B" not in lines
    assert "```\n## not a heading\n# nor this\n```" in log
    assert cli(repo, "check", "core-01").returncode == 0
    r = cli(repo, "parse", "core-01", "--json")
    assert r.returncode == 0, r.stderr


def test_unblock_and_second_finish_stay_outside_fence(repo):
    _run(repo, "--blocked", "needs a board")
    r = cli(repo, "unblock", "core-01")
    assert r.returncode == 0, r.stderr
    r = cli(repo, "finish", "core-01")
    assert r.returncode == 0, r.stderr
    text = (repo / "docs" / "directives" / "core-01.md").read_text()
    assert "```\n## not a heading\n# nor this\n```" in text
    assert "Unblocked:" in text
    assert text.index("Unblocked:") > text.index("# nor this\n```")
    assert cli(repo, "check", "core-01").returncode == 0
    assert cli(repo, "parse", "core-01", "--json").returncode == 0
