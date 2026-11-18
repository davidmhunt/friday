"""Hook parsing of heredocs, and friday's GitHub branch hygiene reports (hook-01).
Run: uv run --with pytest pytest -q tests/test_hook_parsing.py"""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib"))
sys.path.insert(0, str(ROOT / "hooks"))
import friday_core as fc  # noqa: E402
import friday_hook as hook  # noqa: E402

FRIDAY = ROOT / "bin" / "friday"
ACCEPT = "friday accept hook-01"
TEXT = f"run {ACCEPT} then sudo rm things and `{ACCEPT}` and $({ACCEPT})"


def judged(cmd):
    """What the PreToolUse rules that read the command text say about it."""
    return hook.check_deny(cmd), hook.check_accept(cmd)


def refused(cmd):
    return any(judged(cmd))


def test_quoted_heredoc_body_is_data():
    for opener in ("<<'EOF'", '<<"EOF"', "<<-'EOF'"):
        cmd = f"gh pr create --body-file - {opener}\n{TEXT}\nEOF"
        assert not refused(cmd), opener
        assert fc.split_commands(cmd) == [f"gh pr create --body-file - {opener}"], opener


def test_unquoted_heredoc_substitution_is_still_scanned():
    for body in (f"$({ACCEPT})", f"`{ACCEPT}`"):
        cmd = f"cat <<EOF\nplain line\n{body}\nEOF"
        assert hook.check_accept(cmd), body
    assert hook.check_accept(f'cat <<"EOF" ; echo $({ACCEPT})\nx\nEOF')


def test_deny_list_scans_unquoted_heredoc_substitutions_only():
    assert hook.check_deny("cat <<EOF\n$(sudo ls)\nEOF")
    assert hook.check_deny("cat <<EOF\n`sudo ls`\nEOF")
    assert hook.check_deny("cat <<'EOF'\nx\nEOF\nsudo ls")
    assert not hook.check_deny("cat <<'EOF'\n$(sudo ls)\nEOF")


def test_real_accept_after_a_heredoc_is_refused():
    for opener in ("<<'EOF'", "<<EOF"):
        cmd = f"cat {opener}\nharmless\nEOF\n{ACCEPT}"
        assert hook.check_accept(cmd), opener
        assert hook.check_accept(f"cat {opener}\nharmless\nEOF\nbash -c '{ACCEPT}'"), opener
    assert hook.check_accept(f"cat <<'EOF' && {ACCEPT}\nharmless\nEOF")


def test_unterminated_and_here_string_do_not_hide_commands():
    assert hook.check_accept(f"cat <<< x; {ACCEPT}")
    assert hook.check_accept(f"cat <<'EOF'\nbody\nEOF2\n{ACCEPT}")  # no closing line: scanned in full


def test_pretool_hook_end_to_end(tmp_path):
    def run(cmd):
        p = subprocess.run([sys.executable, str(ROOT / "hooks" / "friday_hook.py"), "pretool"],
                           input=json.dumps({"tool_name": "Bash", "cwd": str(tmp_path),
                                             "tool_input": {"command": cmd}}),
                           capture_output=True, text=True)
        return json.loads(p.stdout)["hookSpecificOutput"]["permissionDecision"] if p.stdout.strip() else None

    assert run(f"gh pr create --body-file - <<'EOF'\n{TEXT}\nEOF") is None
    assert run(f"gh pr create --body-file - <<EOF\n$({ACCEPT})\nEOF") == "deny"
    assert run(f"cat <<'EOF'\nx\nEOF\n{ACCEPT}") == "deny"


# --- friday init and status against a fake gh ---

def _fake_gh(tmp_path, delete_on_merge, merged):
    gh = tmp_path / "gh"
    gh.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = auth ]; then exit 0; fi\n'
        f'if [ "$1" = api ]; then echo {delete_on_merge}; exit 0; fi\n'
        'if [ "$1" = pr ]; then\n'
        '  while [ $# -gt 0 ]; do if [ "$1" = --head ]; then h="$2"; fi; shift; done\n'
        f'  case "$h" in {"|".join(merged) or "NONE"}) echo 1;; *) echo 0;; esac; exit 0\n'
        "fi\nexit 1\n")
    gh.chmod(0o755)
    return gh


def _repo(tmp_path):
    r = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", str(r)], check=True)
    subprocess.run(["git", "-C", str(r), "remote", "add", "origin", "git@github.com:acme/widgets.git"], check=True)
    for b in ("friday/done", "friday/open"):
        subprocess.run(["git", "-C", str(r), "update-ref", f"refs/remotes/origin/{b}", "HEAD"], capture_output=True)
    return r


def _friday(repo, gh, *args):
    env = {**os.environ, "FRIDAY_GH": str(gh), "XDG_STATE_HOME": str(repo.parent / "state")}
    return subprocess.run([sys.executable, str(FRIDAY), *args], cwd=repo, env=env, capture_output=True, text=True)


def test_init_reports_and_names_the_command_when_off(tmp_path):
    r = _friday(_repo(tmp_path), _fake_gh(tmp_path, "false", []), "init")
    assert r.returncode == 0
    assert "acme/widgets keeps head branches after merge" in r.stdout
    assert "gh api -X PATCH repos/acme/widgets -F delete_branch_on_merge=true" in r.stdout


def test_init_reports_when_on(tmp_path):
    r = _friday(_repo(tmp_path), _fake_gh(tmp_path, "true", []), "init")
    assert "acme/widgets deletes head branches on merge" in r.stdout
    assert "PATCH" not in r.stdout


def test_init_and_status_skip_quietly_without_gh(tmp_path):
    repo = _repo(tmp_path)
    for args in (("init",), ("status",)):
        r = _friday(repo, tmp_path / "no-such-gh", *args)
        assert "head branches" not in r.stdout and "merged branches" not in r.stdout
        assert "Traceback" not in r.stderr


def test_status_lists_merged_origin_branches_only(tmp_path):
    repo = _repo(tmp_path)
    cp = subprocess.run(["git", "-C", str(repo), "for-each-ref", "refs/remotes/origin/"],
                        capture_output=True, text=True)
    if "origin/friday/done" not in cp.stdout:  # no commit yet: make one so the refs can exist
        env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
               "GIT_COMMITTER_EMAIL": "t@t"}
        subprocess.run(["git", "-C", str(repo), "commit", "-q", "--allow-empty", "-m", "x"], env=env, check=True)
        for b in ("friday/done", "friday/open"):
            subprocess.run(["git", "-C", str(repo), "update-ref", f"refs/remotes/origin/{b}", "HEAD"], check=True)
    before = subprocess.run(["git", "-C", str(repo), "for-each-ref"], capture_output=True, text=True).stdout
    r = _friday(repo, _fake_gh(tmp_path, "true", ["friday/done"]), "status")
    assert "git push origin --delete friday/done" in r.stdout
    assert "friday/open" not in r.stdout
    after = subprocess.run(["git", "-C", str(repo), "for-each-ref"], capture_output=True, text=True).stdout
    assert before == after  # status deleted nothing


def test_non_heredoc_double_angle_does_not_hide_commands():
    cases = [
        "echo $((1<<EOF))\nfriday accept hook-01\nEOF",
        "# <<'EOF'\nfriday accept hook-01\nEOF",
        "echo hi # <<EOF\nfriday accept hook-01",
        "(( x = 1<<2 ))\nfriday accept hook-01\n2",
        "cat <<E'OF'\nx\nEOF\nfriday accept hook-01",
    ]
    for cmd in cases:
        assert "friday accept hook-01" in fc.split_commands(cmd), cmd
        assert refused(cmd), cmd


def test_fail_closed_heredoc_cases_are_still_scanned():
    cases = [
        "cat <<EOF+\nx\nEOF+\nfriday accept hook-01",
        "cat <<EOF@\nbody\nfriday accept hook-01\nEOF@",
        "cat <<'EOF'+\nfriday accept hook-01\nEOF+",
        "cat <<EOF$x\nfriday accept hook-01\nEOF",
        "echo $[1<<EOF]\nfriday accept hook-01\nEOF",
        "echo ${x:-<<EOF}\nfriday accept hook-01\nEOF",
        "cat <<'EOF'\nfriday accept hook-01",  # missing closing line
    ]
    for cmd in cases:
        assert refused(cmd), cmd
