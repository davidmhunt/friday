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
    "echo x >| f",
    "make >& log",
    "make &> log",
    "make 2>&1 >| f",
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
    "make >&2",
    "make 2>&1 >&-",
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


def test_split_commands_ignores_quoted_and_escaped_substitutions():
    from friday_core import split_commands
    assert split_commands("gh issue create --body 'use `python3 -` here'") == ["gh issue create --body 'use `python3 -` here'"]
    assert split_commands("echo '$(python3 -)'") == ["echo '$(python3 -)'"]
    assert split_commands('gh issue create --body "use \\`python3 -\\` here"') == \
        ['gh issue create --body "use \\`python3 -\\` here"']
    assert "python3 -" in split_commands('echo "$(python3 -)"')      # still run: double quotes expand
    assert "python3 -" in split_commands("echo `python3 -`")


def test_run_only_ignores_single_quoted_and_escaped_substitutions():
    cfg = {"run_only": ["python3"]}
    assert hook.check_run_only("gh issue create --body 'use `python3 -` here'", cfg) is None
    assert hook.check_run_only('gh issue create --body "use \\`python3 -\\` here"', cfg) is None


def test_invalid_value_is_a_check_error_and_loads_as_allow(tmp_path):
    import friday_core as fc
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "friday.json").write_text('{"bash_file_io": "maybe"}')
    issues = fc.config_issues(tmp_path)
    assert any(i.level == "error" and "bash_file_io" in i.message for i in issues)
    assert fc.load_config(tmp_path)["bash_file_io"] == "allow"


def test_pre_approved_command_is_still_denied(tmp_path, monkeypatch, capsys):
    import json, subprocess
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "friday.json").write_text('{"bash_file_io": "deny"}')
    monkeypatch.setattr(hook, "check_preapproved", lambda cmd, cwd: ("allow", "pre-approved"))
    hook.pretool({"tool_name": "Bash", "tool_input": {"command": "cat notes.md"}, "cwd": str(tmp_path), "session_id": "s"})
    out = json.loads(capsys.readouterr().out)["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny"
    hook.pretool({"tool_name": "Bash", "tool_input": {"command": "ls"}, "cwd": str(tmp_path), "session_id": "s"})
    assert json.loads(capsys.readouterr().out)["hookSpecificOutput"]["permissionDecision"] == "allow"


def test_init_prints_the_bash_file_io_hint(tmp_path):
    import os, subprocess
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    r = subprocess.run([sys.executable, str(ROOT / "bin" / "friday"), "init"], cwd=tmp_path, capture_output=True,
                       text=True, env={**os.environ, "HOME": str(tmp_path)})
    assert r.returncode == 0, r.stderr
    assert '"bash_file_io": "deny"' in r.stdout
