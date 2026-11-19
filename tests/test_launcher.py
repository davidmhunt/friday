"""bin/friday-python resolves the interpreter; hooks.json runs every hook through it."""
import json
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LAUNCHER = ROOT / "bin" / "friday-python"


def _exe(path, body):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(0o755)
    return path


def _run(tmp_path, record=None, uv=None, python3=True):
    home = tmp_path / "home"
    fake = tmp_path / "bin"
    fake.mkdir(exist_ok=True)
    home.mkdir(exist_ok=True)
    shutil.copy(shutil.which("head"), fake / "head")
    if record:
        rec = home / ".local" / "state" / "friday" / "python"
        rec.parent.mkdir(parents=True, exist_ok=True)
        rec.write_text(record + "\n")
    if uv:
        _exe(fake / "uv", f'echo "{uv}"\n')
    if python3:
        _exe(fake / "py3", 'echo "system-python $*"\n')
        (fake / "python3").symlink_to(fake / "py3")
    env = {"HOME": str(home), "PATH": str(fake)}
    return subprocess.run(["/bin/sh", str(LAUNCHER), "a", "b"], env=env,
                          capture_output=True, text=True)


def test_recorded_path_used(tmp_path):
    py = _exe(tmp_path / "rec-python", 'echo "recorded $*"\n')
    r = _run(tmp_path, record=str(py), uv=str(tmp_path / "nope"))
    assert r.stdout.strip() == "recorded a b" and r.stderr == ""


def test_stale_record_falls_to_uv(tmp_path):
    py = _exe(tmp_path / "uv-python", 'echo "uvpy $*"\n')
    r = _run(tmp_path, record=str(tmp_path / "gone"), uv=str(py))
    assert r.stdout.strip() == "uvpy a b" and r.stderr == ""


def test_uv_find_when_no_record(tmp_path):
    py = _exe(tmp_path / "uv-python", 'echo "uvpy $*"\n')
    r = _run(tmp_path, uv=str(py))
    assert r.stdout.strip() == "uvpy a b"


def test_python3_fallback_warns(tmp_path):
    r = _run(tmp_path)
    assert r.stdout.strip() == "system-python a b"
    assert "friday install" in r.stderr and "python3" in r.stderr


def test_hooks_json_uses_launcher():
    data = json.loads((ROOT / "hooks" / "hooks.json").read_text())
    cmds = [h["command"] for groups in data["hooks"].values()
            for g in groups for h in g["hooks"]]
    assert cmds
    for c in cmds:
        assert c.startswith('"${CLAUDE_PLUGIN_ROOT}/bin/friday-python" "${CLAUDE_PLUGIN_ROOT}/hooks/friday_hook.py" ')
        assert "python3" not in c
