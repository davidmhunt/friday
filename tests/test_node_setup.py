"""friday nodes --setup against a fake ssh that runs the remote script locally under a temp HOME."""
import json
import os
import subprocess
import sys
from pathlib import Path

from helpers import tool_bin  # noqa: E402

FRIDAY = Path(__file__).resolve().parent.parent / "bin" / "friday"
NODES = '''[node.laptop]
role = "master"
ssh = "me@laptop"
repos = "~/r"
plugin_dir = "~/f"
[node.bot]
role = "target"
ssh = "me@bot"
'''
FAKE = '#!/bin/bash\necho "$@" >> "$0.argv"\nexec bash -s\n'


def _run(tmp_path, *args, settings=None, stdin=subprocess.DEVNULL, path=None):
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True, exist_ok=True)
    if not (home / "f").exists():
        (home / "f").symlink_to(FRIDAY.parent.parent)  # the node's plugin_dir, for the remote install
    cfg = home / ".claude" / "settings.json"
    if settings is not None:
        cfg.write_text(settings)
    (tmp_path / "n.toml").write_text(NODES)
    ssh = tmp_path / "fakessh"
    ssh.write_text(FAKE)
    ssh.chmod(0o755)
    ctl = tmp_path / "fakectl"
    ctl.write_text('#!/bin/bash\necho "$@" >> "$0.argv"\n')
    ctl.chmod(0o755)
    env = dict(os.environ, FRIDAY_NODES=str(tmp_path / "n.toml"), FRIDAY_SSH=str(ssh), HOME=str(home),
               FRIDAY_SYSTEMCTL=str(ctl))
    env["PATH"] = path if path is not None else _tools(tmp_path, gh="ok", claude="in", uv="fake")  # fakes, never a real gh/claude
    r = subprocess.run([sys.executable, str(FRIDAY), "nodes", *args], env=env, capture_output=True,
                       text=True, cwd=tmp_path, stdin=stdin)
    return r, cfg


def test_setup_merges_and_backs_up(tmp_path):
    old = json.dumps({"theme": "dark", "permissions": {"allow": ["Bash(ls)"]}, "skipAutoPermissionPrompt": False})
    r, cfg = _run(tmp_path, "--setup", "laptop", "--yes", settings=old)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "skipWorkflowUsageWarning" in r.stdout and "settings.json" in r.stdout
    d = json.loads(cfg.read_text())
    assert d == {"theme": "dark", "permissions": {"allow": ["Bash(ls)"]},
                 "skipAutoPermissionPrompt": True, "skipWorkflowUsageWarning": True}
    assert (cfg.parent / "settings.json.friday-bak").read_text() == old
    assert not [p for p in cfg.parent.iterdir() if p.name.startswith(".settings.json.friday-")]
    # a second run keeps the first backup
    _run(tmp_path, "--setup", "laptop", "--yes")
    assert (cfg.parent / "settings.json.friday-bak").read_text() == old


def test_setup_creates_missing_file(tmp_path):
    r, cfg = _run(tmp_path, "--setup", "laptop", "--yes")
    assert r.returncode == 0
    assert json.loads(cfg.read_text()) == {"skipWorkflowUsageWarning": True, "skipAutoPermissionPrompt": True}


def test_setup_refuses_without_tty(tmp_path):
    old = '{"theme": "dark"}'
    r, cfg = _run(tmp_path, "--setup", "laptop", settings=old)
    assert r.returncode == 1 and "--yes" in r.stdout
    assert "skipWorkflowUsageWarning" in r.stdout  # shows what it would set
    assert "prerequisites" in r.stdout  # the probe runs first; the settings script does not
    assert cfg.read_text() == old and "FRIDAY_SETUP" not in (tmp_path / "fakessh.argv").read_text()
    assert not (cfg.parent / "settings.json.friday-bak").exists()


def test_setup_unparsable_file_untouched(tmp_path):
    r, cfg = _run(tmp_path, "--setup", "laptop", "--yes", settings="{bad")
    assert r.returncode == 1 and "not a JSON object" in r.stdout
    assert cfg.read_text() == "{bad"


def test_setup_unknown_and_target_node(tmp_path):
    r, _ = _run(tmp_path, "--setup", "nope", "--yes")
    assert r.returncode == 1 and not (tmp_path / "fakessh.argv").exists()
    r, cfg = _run(tmp_path, "--setup", "bot", "--yes")  # a target: prerequisites and the registry edit, nothing changed
    assert r.returncode == 1 and "prerequisites" in r.stdout and 'role = "worker"' in r.stdout
    assert not cfg.exists() and not (tmp_path / "home" / ".config" / "friday").exists()


def _check(tmp_path, settings):
    r, _ = _run(tmp_path, "--check", settings=settings)
    return r.stdout


def test_check_reports_prompts_from_real_settings_file(tmp_path):
    both = '{"skipWorkflowUsageWarning": true, "skipAutoPermissionPrompt": true}'
    cases = [
        (None, True, True),
        ('{"theme": "dark"}', True, True),
        ('{"skipWorkflowUsageWarning": true}', False, True),
        ('{"skipAutoPermissionPrompt": true}', True, False),
        (both, False, False),
        ("{bad", True, True),
    ]
    for i, (content, wf, auto) in enumerate(cases):
        sub = tmp_path / str(i)
        sub.mkdir()
        out = _check(sub, content)
        assert ("workflow prompt: run `friday nodes --setup laptop`" in out) == wf, (content, out)
        assert ("auto-mode prompt: run `friday nodes --setup laptop`" in out) == auto, (content, out)


def test_setup_then_check_clears_prompts(tmp_path):
    _run(tmp_path, "--setup", "laptop", "--yes", settings="{}")
    out = _check(tmp_path, None)
    assert "workflow prompt" not in out and "auto-mode prompt" not in out


def test_setup_installs_push_timer(tmp_path):
    r, cfg = _run(tmp_path, "--setup", "laptop", "--yes")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "friday-push.timer" in r.stdout
    unit = cfg.parent.parent / ".config" / "systemd" / "user"
    svc = (unit / "friday-push.service").read_text()
    assert "ExecStart=%h/f/bin/friday status --push" in svc and "@PLUGIN_DIR@" not in svc
    assert "OnUnitActiveSec=30s" in (unit / "friday-push.timer").read_text()
    assert (tmp_path / "fakectl.argv").read_text().splitlines() == [
        "--user daemon-reload", "--user enable --now friday-push.timer"]


def test_setup_without_confirmation_installs_no_timer(tmp_path):
    r, cfg = _run(tmp_path, "--setup", "laptop")
    assert r.returncode == 1
    assert not (tmp_path / "home" / ".config" / "systemd").exists()
    assert not (tmp_path / "fakectl.argv").exists()


def _tools(tmp_path, uv=True, gh=None, claude=None):
    """A PATH holding the system tools except uv/gh/claude, plus fakes: gh in {None, 'ok', 'nologin'}, claude in
    {None, 'in', 'out'}."""
    b = Path(tool_bin(tmp_path / "tools"))

    def fake(name, body):
        f = b / name
        f.unlink(missing_ok=True)
        f.write_text("#!/bin/bash\n" + body + "\n")
        f.chmod(0o755)
    if uv == "fake":  # a uv that installs and finds a fake interpreter under the temp HOME
        from test_install import fake_uv
        (b / "uv").unlink(missing_ok=True)
        (b / "uv").symlink_to(Path(fake_uv(tmp_path, real=True)) / "uv")
    elif uv:
        fake("uv", "exit 0")
    if gh:
        fake("gh", "exit 0" if gh == "ok" else "exit 1")
    if claude:
        fake("claude", 'echo \'{"loggedIn": %s}\'' % ("true" if claude == "in" else "false"))
    return str(b)


def test_check_reports_missing_prerequisites_with_fixes(tmp_path):
    r, _ = _run(tmp_path, "--check", settings="{}", path=_tools(tmp_path, uv=False, gh="nologin", claude="out"))
    out = r.stdout
    assert "install uv on laptop" in out and "https://docs.astral.sh/uv/getting-started/installation/" in out
    assert "run `gh auth login` on laptop" in out
    assert "run `claude` and `/login` on laptop" in out and "not signed in" in out


def test_check_prerequisites_ok_report_no_fixes(tmp_path):
    r, _ = _run(tmp_path, "--check", settings="{}", path=_tools(tmp_path, gh="ok", claude="in"))
    assert "install uv" not in r.stdout and "gh auth login" not in r.stdout and "/login" not in r.stdout


def test_setup_target_prints_prerequisites_and_registry_edit_runs_no_settings(tmp_path):
    r, cfg = _run(tmp_path, "--setup", "bot", "--yes", path=_tools(tmp_path, uv=False, gh="nologin", claude="out"))
    assert r.returncode == 1
    assert "prerequisites on bot" in r.stdout and "uv: missing" in r.stdout
    assert "gh auth: missing" in r.stdout and "claude signed in: missing" in r.stdout
    assert 'role = "worker"' in r.stdout and "repos" in r.stdout and "plugin_dir" in r.stdout
    assert "FRIDAY_SETUP" not in (tmp_path / "fakessh.argv").read_text()
    assert not cfg.exists()


def test_setup_worker_prints_prerequisites_before_settings_prompt(tmp_path):
    r, _ = _run(tmp_path, "--setup", "laptop", path=_tools(tmp_path, uv=False, gh="nologin", claude="out"))
    out = r.stdout
    assert r.returncode == 1
    assert out.index("prerequisites on laptop") < out.index("will set these keys")
    assert "uv: missing" in out and "gh auth: missing" in out and "claude signed in: missing" in out
