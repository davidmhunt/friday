"""bash_file_io: deny rule and quote-aware run_only (tt-07).
Run: uv run --with pytest pytest -q tests/test_bash_file_io.py"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib"))
sys.path.insert(0, str(ROOT / "hooks"))
import friday_hook as hook  # noqa: E402

DENY = {"bash_file_io": "deny"}


@pytest.mark.parametrize("cmd", [
    "cat notes.md",
    "sed -n 1,60p f",
    "grep -n x file",
    "tail -n +1 runs/*/*.txt",
    "printf x >> notes.md",
    "printf x > out.txt",
    "sed -i s/a/b/ f",
    "sed -i.bak s/a/b/ f",
    "echo hi | tee f",
    "head -5 f",
    "rg foo src",
    "awk '{print $1}' f",
    "cat <<EOF\nhi\nEOF",
    "python3 - <<'EOF'\nprint(1)\nEOF",
    "python3 -",
    "git log | head -5 && cat notes.md",
])
def test_denied(cmd):
    assert hook.check_bash_file_io(cmd, DENY)


@pytest.mark.parametrize("cmd", [
    "make 2>&1 | tail -3",
    "git log | head -5",
    "ls runs",
    "uv run pytest -q > /dev/null",
    "echo hi",
    "cmd 2>/dev/null | grep x",
    "git log | grep -n fix | head",
    "python3 x.py",
])
def test_allowed(cmd):
    assert hook.check_bash_file_io(cmd, DENY) is None


@pytest.mark.parametrize("cfg", [{}, {"bash_file_io": "allow"}])
def test_default_and_allow_change_nothing(cfg):
    for cmd in ("cat notes.md", "printf x >> notes.md", "python3 - <<EOF\nx\nEOF"):
        assert hook.check_bash_file_io(cmd, cfg) is None


def test_reason_names_file_tools():
    r = hook.check_bash_file_io("cat notes.md", DENY)
    for name in ("Read", "Grep", "Glob", "Edit", "Write"):
        assert name in r


def test_run_only_ignores_quoted_words():
    cfg = {"run_only": ["python3"]}
    assert hook.check_run_only('gh issue create --body "use python3 - here"', cfg) is None
    assert hook.check_run_only("python3 x.py", cfg)
