"""bash_file_io: deny rule and quote-aware run_only (tt-07).
Run: uv run --with pytest --with pyyaml pytest -q tests/test_bash_file_io.py"""
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


def test_split_commands_literal_quotes_ignores_quoted_and_escaped_substitutions():
    from friday_core import split_commands as sc

    def lit(c):
        return sc(c, literal_quotes=True)
    assert lit("gh issue create --body 'use `python3 -` here'") == ["gh issue create --body 'use `python3 -` here'"]
    assert lit("echo '$(python3 -)'") == ["echo '$(python3 -)'"]
    assert lit('gh issue create --body "use \\`python3 -\\` here"') == \
        ['gh issue create --body "use \\`python3 -\\` here"']
    assert "python3 -" in lit('echo "$(python3 -)"')      # still run: double quotes expand
    assert "python3 -" in lit("echo `python3 -`")


def test_split_commands_default_extracts_every_substitution():
    """Fail closed: an inner shell (bash -c, ssh) runs text that is literal to the local shell."""
    from friday_core import split_commands as sc
    for c in ("echo '$(python3 -)'", "echo '`python3 -`'", 'echo "\\`python3 -\\`"', 'echo "\\$(python3 -)"'):
        assert any(p.startswith("python3 -") for p in sc(c)), c


INNER_SHELL = [
    "bash -c '$(friday {v} {a})'",
    "ssh host '$(friday {v} {a})'",
    'bash -c "\\`friday {v} {a}\\`"',
    'ssh host "\\$(friday {v} {a})"',
]


@pytest.mark.parametrize("tmpl", INNER_SHELL)
@pytest.mark.parametrize("v,a", [("accept", "x"), ("approve", "--goal g")])
def test_accept_guard_sees_substitutions_inside_inner_shell_quotes(tmpl, v, a):
    cmd = tmpl.format(v=v, a=a)
    assert hook.check_accept(cmd), cmd


def test_run_only_ignores_single_quoted_and_escaped_substitutions():
    cfg = {"run_only": ["python3"]}
    assert hook.check_run_only("gh issue create --body 'use `python3 -` here'", cfg) is None
    assert hook.check_run_only('gh issue create --body "use \\`python3 -\\` here"', cfg) is None
    assert hook.check_bash_file_io("gh issue create --body 'use `python3 -` here'", DENY) is None


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


# ---- the active directive's own Verify line is exempt from bash_file_io (vf-01, #33)

VERIFY_LINE = "test -s docs/x.md && grep -q '^## Verdict' docs/x.md && ./run pytest -q"


def _verify_repo(tmp_path, verify=VERIFY_LINE, marker_id="vf-x"):
    import subprocess
    import friday_core as fc
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "docs" / "directives").mkdir(parents=True)
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "friday.json").write_text('{"bash_file_io": "deny"}')
    (tmp_path / "docs" / "directives" / "vf-x.md").write_text(
        f"# vf-x: t\nStatus: approved\nGoal: g\nNode: any\nDeliverable: code\nLand: goal\n"
        f"Verify: {verify}\nHardware: none\n\n## Goal\nx\n\n## Steps\n1. a\n\n## Log\n")
    if marker_id:
        fc.write_marker(tmp_path, {"id": marker_id})
    return tmp_path


def test_active_verify_line_is_exempt(tmp_path):
    repo = _verify_repo(tmp_path)
    assert hook.check_bash_file_io(VERIFY_LINE, DENY) is not None   # no cwd: still denied
    assert hook.check_bash_file_io(VERIFY_LINE, DENY, repo) is None
    assert hook.check_bash_file_io("  " + VERIFY_LINE + "\n", DENY, repo) is None


def test_verify_exemption_needs_this_directives_marker_and_exact_bytes(tmp_path):
    (tmp_path / "r1").mkdir()
    repo = _verify_repo(tmp_path / "r1", marker_id="other-01")      # another directive's marker
    assert hook.check_bash_file_io(VERIFY_LINE, DENY, repo)
    (tmp_path / "r2").mkdir()
    repo2 = _verify_repo(tmp_path / "r2")
    assert hook.check_bash_file_io(VERIFY_LINE.replace("x.md", "y.md", 1), DENY, repo2)
    assert hook.check_bash_file_io(VERIFY_LINE + "x", DENY, repo2)
    assert hook.check_bash_file_io("cat notes.md", DENY, repo2)
    (tmp_path / "r3").mkdir()
    repo3 = _verify_repo(tmp_path / "r3", marker_id=None)           # no marker
    assert hook.check_bash_file_io(VERIFY_LINE, DENY, repo3)


def test_verify_line_matching_the_deny_list_is_still_denied(tmp_path, capsys):
    import json
    line = "test -s docs/x.md && git push --force origin main"
    repo = _verify_repo(tmp_path, verify=line)
    assert hook.check_bash_file_io(line, DENY, repo) is None
    hook.pretool({"tool_name": "Bash", "tool_input": {"command": line}, "cwd": str(repo), "session_id": "s"})
    out = json.loads(capsys.readouterr().out)["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny"
