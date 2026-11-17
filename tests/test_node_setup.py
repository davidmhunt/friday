"""friday nodes --setup against a fake ssh that runs the remote script locally under a temp HOME."""
import json
import os
import subprocess
import sys
from pathlib import Path

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


def _run(tmp_path, *args, settings=None, stdin=subprocess.DEVNULL):
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True, exist_ok=True)
    cfg = home / ".claude" / "settings.json"
    if settings is not None:
        cfg.write_text(settings)
    (tmp_path / "n.toml").write_text(NODES)
    ssh = tmp_path / "fakessh"
    ssh.write_text(FAKE)
    ssh.chmod(0o755)
    env = dict(os.environ, FRIDAY_NODES=str(tmp_path / "n.toml"), FRIDAY_SSH=str(ssh), HOME=str(home))
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
    assert cfg.read_text() == old and not (tmp_path / "fakessh.argv").exists()


def test_setup_unparsable_file_untouched(tmp_path):
    r, cfg = _run(tmp_path, "--setup", "laptop", "--yes", settings="{bad")
    assert r.returncode == 1 and "not a JSON object" in r.stdout
    assert cfg.read_text() == "{bad"


def test_setup_unknown_and_target_node(tmp_path):
    for name in ("nope", "bot"):
        r, _ = _run(tmp_path, "--setup", name, "--yes")
        assert r.returncode == 1 and not (tmp_path / "fakessh.argv").exists()
