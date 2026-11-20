"""spec-02: the tutorial's commands and every example goal/directive in the tutorial and recipes work.
Run: uv run --with pytest --with pyyaml pytest -q tests/test_tutorial.py"""
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CLI = ROOT / "bin" / "friday"
DOCS = ROOT / "docs"
PAGES = [DOCS / "getting-started.md", DOCS / "recipes" / "research.md",
         DOCS / "recipes" / "robot.md", DOCS / "recipes" / "pcb.md"]


def blocks(page):
    return re.findall(r"^```markdown\n(.*?)^```", page.read_text(), re.S | re.M)


def classify(page):
    """Return (goals, directives) as {id: text} from the page's markdown blocks."""
    goals, dirs = {}, {}
    for b in blocks(page):
        m = re.match(r"# ([a-z0-9-]+): ", b)
        if not m:
            continue
        if re.search(r"^Base: ", b, re.M):
            goals[m.group(1)] = b
        elif re.search(r"^Goal: ", b, re.M):
            dirs[m.group(1)] = b
    return goals, dirs


def approve(text):
    return text.replace("Status: proposed", "Status: approved", 1)


def git(r, *a):
    return subprocess.run(["git", "-C", str(r), *a], capture_output=True, text=True, check=True).stdout


def cli(r, *a):
    return subprocess.run([sys.executable, str(CLI), *a], cwd=r, capture_output=True, text=True)


def new_repo(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(r)], check=True)
    for k, v in (("user.name", "t"), ("user.email", "t@t")):
        git(r, "config", k, v)
    (r / "docs/goals").mkdir(parents=True)
    (r / "docs/directives").mkdir(parents=True)
    return r


def write_plan(r, goals, dirs, transform=lambda t: t):
    for k, v in goals.items():
        (r / f"docs/goals/{k}.md").write_text(transform(v))
    for k, v in dirs.items():
        (r / f"docs/directives/{k}.md").write_text(transform(v))


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_every_example_passes_check(page, tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    goals, dirs = classify(page)
    assert goals and dirs, f"{page.name} has no example goal and directives"
    r = new_repo(tmp_path)
    write_plan(r, goals, dirs)
    out = cli(r, "check", "--all")
    assert out.returncode == 0, out.stdout + out.stderr
    assert "0 error(s)" in out.stdout
    # the goal lists exactly the directives shown
    for g in goals.values():
        for d in re.findall(r"^\d+\. ([a-z0-9-]+):", g, re.M):
            assert d in dirs, f"{page.name}: goal lists {d} but no directive file is shown"
    # approved copies pass too
    write_plan(r, goals, dirs, approve)
    out = cli(r, "check", "--all")
    assert out.returncode == 0, out.stdout + out.stderr


def test_tutorial_commands_in_order(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    goals, dirs = classify(DOCS / "getting-started.md")
    goal, d = goals["hello-notes"], dirs["note-01"]
    r = new_repo(tmp_path)
    for p in ("docs/goals", "docs/directives"):
        (r / p).rmdir()
    (r / "docs").rmdir()

    # friday init, then the setup commit the tutorial shows
    out = cli(r, "init")
    assert out.returncode == 0, out.stderr
    assert (r / ".claude/settings.json").exists() and (r / ".git/hooks/commit-msg").exists()
    (r / "CLAUDE.md").write_text("# project\n")
    (r / ".gitignore").write_text("runs/\n")
    git(r, "add", ".gitignore", "CLAUDE.md", ".claude")
    git(r, "commit", "-qm", "Set up friday")

    # the tutorial's goal and directive, approved, then check
    (r / "docs/goals").mkdir(parents=True)
    (r / "docs/directives").mkdir(parents=True)
    write_plan(r, {"hello-notes": goal}, {"note-01": d}, approve)
    out = cli(r, "check", "--all")
    assert out.returncode == 0, out.stdout + out.stderr
    git(r, "add", "docs")
    git(r, "commit", "-qm", "Plan hello-notes\n\nDirective: note-01")

    # start, do the step, finish
    s = cli(r, "start", "note-01")
    assert s.returncode == 0, s.stderr
    assert git(r, "branch", "--show-current").strip() in ("friday/hello-notes", "friday/note-01")
    (r / "NOTES.md").write_text("What this repo is for.\n")
    git(r, "add", "NOTES.md")
    git(r, "commit", "-qm", "note-01 step 1: NOTES.md\n\nDirective: note-01")
    f = cli(r, "finish", "note-01")
    assert f.returncode == 0, f.stderr
    assert "Status: done" in (r / "docs/directives/note-01.md").read_text()

    # the Allowed commands snippet from the tutorial, in a directive
    page = (DOCS / "getting-started.md").read_text()
    allowed = re.search(r"^```markdown\n(## Allowed commands\n.*?)^```", page, re.S | re.M).group(1)
    d2 = approve(d.replace("note-01", "note-02").replace("Add NOTES.md and its check", "Bench it")
                 .replace("## Log", allowed + "\n## Log"))
    g2 = approve(goal.replace("hello-notes", "bench").replace("note-01", "note-02")
                 .replace("Add NOTES.md and its check", "Bench it"))
    d2 = d2.replace("Goal: hello-notes", "Goal: bench")
    (r / "docs/goals/bench.md").write_text(g2)
    (r / "docs/directives/note-02.md").write_text(d2)
    out = cli(r, "check", "note-02")
    assert out.returncode == 0, out.stdout + out.stderr
    assert "./run tools/bench.sh *" in d2

    # a goal with Accept: user reaches awaiting review, then accept
    d3 = approve(d.replace("note-01", "note-03").replace("Goal: hello-notes", "Goal: review")
                 .replace("Deliverable: code\n", "Deliverable: code\nAccept: user\n")
                 .replace("## Out of scope", "## Review\n- open NOTES.md and read it\n\n## Out of scope"))
    g3 = approve(goal.replace("hello-notes", "review").replace("note-01", "note-03"))
    (r / "docs/goals/review.md").write_text(g3)
    (r / "docs/directives/note-03.md").write_text(d3)
    out = cli(r, "check", "--all")
    assert out.returncode == 0, out.stdout + out.stderr
    # amendments to the plan go on Base, not on the goal branch
    git(r, "switch", "-q", "main")
    git(r, "add", "docs")
    git(r, "commit", "-qm", "Plan more\n\nDirective: note-03")
    assert cli(r, "start", "note-03").returncode == 0
    f = cli(r, "finish", "note-03")
    assert f.returncode == 0, f.stderr
    assert "Status: awaiting review" in (r / "docs/directives/note-03.md").read_text()
    assert "friday accept note-03" in f.stdout
    a = cli(r, "accept", "note-03")
    assert a.returncode == 0, a.stderr
    assert "Status: done" in (r / "docs/directives/note-03.md").read_text()
