"""friday install / uninstall against a temp bin dir."""
import os
import subprocess
import sys
from pathlib import Path

from helpers import tool_bin  # noqa: E402

FRIDAY = Path(__file__).resolve().parent.parent / "bin" / "friday"


def PY312(tmp_path):
    return tmp_path / "home" / ".local" / "share" / "friday" / "python" / "py312"


def fake_uv(tmp_path, real=False):
    """A `uv` that 'installs' and 'finds' a fake interpreter; returns the directory to put on PATH."""
    d = tmp_path / "fakeuv"
    d.mkdir(exist_ok=True)
    py = tmp_path / "home" / ".local" / "share" / "friday" / "python" / "py312"
    py.parent.mkdir(parents=True, exist_ok=True)
    py.write_text(f'#!/bin/sh\nexec {sys.executable} "$@"\n' if real else "#!/bin/sh\n")
    py.chmod(0o755)
    uv = d / "uv"
    uv.write_text(f'#!/bin/sh\n[ "$2" = find ] && echo {py}\nexit 0\n')
    uv.chmod(0o755)
    return str(d)


def run(tmp_path, *args, path=""):
    base = path or os.environ["PATH"]
    env = {**os.environ, "HOME": str(tmp_path / "home"), "PATH": f"{fake_uv(tmp_path)}:{base}"}
    return subprocess.run([sys.executable, str(FRIDAY), *args, "--bin-dir", str(tmp_path / "bin")],
                          capture_output=True, text=True, env=env, cwd=tmp_path)


def fake_checkout(tmp_path, name):
    f = tmp_path / name / "bin" / "friday"
    f.parent.mkdir(parents=True)
    f.write_text("#!/bin/sh\n")
    (tmp_path / name / "lib").mkdir()
    (tmp_path / name / "lib" / "friday_core.py").write_text("")
    return f


def test_fresh_install_and_idempotent(tmp_path):
    r = run(tmp_path, "install")
    assert r.returncode == 0, r.stderr
    link = tmp_path / "bin" / "friday"
    assert link.is_file() and not link.is_symlink()
    assert link.read_text().splitlines()[-1].endswith(f"{FRIDAY.resolve()} \"$@\"")
    rec = tmp_path / "home" / ".local" / "state" / "friday" / "python"
    assert rec.read_text().strip() == str(PY312(tmp_path))
    assert str(PY312(tmp_path)) in link.read_text()
    r = run(tmp_path, "install")
    assert r.returncode == 0 and link.is_file()


def test_repoint_from_other_checkout(tmp_path):
    other = fake_checkout(tmp_path, "other")
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "friday").symlink_to(other)
    r = run(tmp_path, "install")
    assert r.returncode == 0
    assert str(other) in r.stdout
    f = tmp_path / "bin" / "friday"
    assert not f.is_symlink() and str(FRIDAY.resolve()) in f.read_text()


def test_refuse_regular_file_and_foreign_link(tmp_path):
    (tmp_path / "bin").mkdir()
    f = tmp_path / "bin" / "friday"
    f.write_text("mine")
    assert run(tmp_path, "install").returncode == 1
    assert f.read_text() == "mine"
    f.unlink()
    foreign = tmp_path / "tool"
    foreign.write_text("x")
    f.symlink_to(foreign)
    assert run(tmp_path, "install").returncode == 1
    assert os.readlink(f) == str(foreign)


def test_path_hint(tmp_path):
    b = str(tmp_path / "bin")
    r = run(tmp_path, "install", path="/usr/bin:/bin")
    assert "not on PATH" in r.stdout and "~/.profile" in r.stdout and b in r.stdout
    r = run(tmp_path, "install", path=f"{b}:/usr/bin:/bin")
    assert "is on PATH" in r.stdout and "not on PATH" not in r.stdout


def test_uninstall(tmp_path):
    run(tmp_path, "install")
    r = run(tmp_path, "uninstall")
    assert r.returncode == 0 and "removed" in r.stdout
    assert not (tmp_path / "bin" / "friday").exists()
    assert not (tmp_path / "home" / ".local" / "state" / "friday" / "python").exists()
    r = run(tmp_path, "uninstall")
    assert r.returncode == 0 and len(r.stdout.strip().splitlines()) == 1


def test_uninstall_other_checkout_ok_and_refusals(tmp_path):
    other = fake_checkout(tmp_path, "other")
    (tmp_path / "bin").mkdir()
    f = tmp_path / "bin" / "friday"
    f.symlink_to(other)
    assert run(tmp_path, "uninstall").returncode == 0 and not f.is_symlink()
    f.write_text("mine")
    assert run(tmp_path, "uninstall").returncode == 1 and f.read_text() == "mine"
    f.unlink()
    foreign = tmp_path / "tool"
    foreign.write_text("x")
    f.symlink_to(foreign)
    assert run(tmp_path, "uninstall").returncode == 1 and f.is_symlink()


def _setup(tmp_path, *extra, stdin=subprocess.DEVNULL):
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    root = FRIDAY.parent.parent
    (tmp_path / "n.toml").write_text(
        f'[node.laptop]\nrole = "master"\nssh = "me@laptop"\nrepos = "~/r"\nplugin_dir = "{root}"\n')
    ssh = tmp_path / "fakessh"
    ssh.write_text('#!/bin/bash\nexec bash -s\n')
    ssh.chmod(0o755)
    ctl = tmp_path / "fakectl"
    ctl.write_text("#!/bin/bash\n")
    ctl.chmod(0o755)
    env = {**os.environ, "HOME": str(home), "FRIDAY_NODES": str(tmp_path / "n.toml"),
           "FRIDAY_SSH": str(ssh), "FRIDAY_SYSTEMCTL": str(ctl),
           "PATH": f"{fake_uv(tmp_path, real=True)}:{os.environ['PATH']}"}
    return subprocess.run([sys.executable, str(FRIDAY), "nodes", "--setup", "laptop", *extra],
                          capture_output=True, text=True, env=env, stdin=stdin), home


def test_setup_runs_remote_install_after_confirmation(tmp_path):
    r, home = _setup(tmp_path, "--yes")
    assert r.returncode == 0, r.stdout + r.stderr
    link = home / ".local" / "bin" / "friday"
    assert link.is_file() and str(FRIDAY) in link.read_text()


def test_setup_without_confirmation_installs_nothing(tmp_path):
    r, home = _setup(tmp_path)
    assert r.returncode == 1
    assert not (home / ".local" / "bin" / "friday").exists()


def _check(tmp_path):
    r, home = _setup(tmp_path, stdin=subprocess.DEVNULL)  # also leaves a home; reuse its node file
    return home


def _run_check(tmp_path, home):
    env = {**os.environ, "HOME": str(home), "FRIDAY_NODES": str(tmp_path / "n.toml"),
           "FRIDAY_SSH": str(tmp_path / "fakessh"), "PATH": tool_bin(tmp_path / "safebin")}  # no real friday, gh or claude
    return subprocess.run([sys.executable, str(FRIDAY), "nodes", "--check"],
                          capture_output=True, text=True, env=env)


def test_check_reports_ok_missing_and_wrong_target(tmp_path):
    home = _check(tmp_path)  # without --yes: nothing installed, node file written
    link = home / ".local" / "bin" / "friday"
    r = _run_check(tmp_path, home)
    assert "friday on PATH: missing" in r.stdout and "friday nodes --setup laptop" in r.stdout
    link.parent.mkdir(parents=True, exist_ok=True)
    link.write_text(f'#!/bin/sh\n# friday shim (test)\nexec python3 {FRIDAY} "$@"\n')
    r = _run_check(tmp_path, home)
    assert "friday on PATH: ok" in r.stdout and "friday on PATH: missing" not in r.stdout
    other = fake_checkout(tmp_path, "other")
    link.unlink()
    link.symlink_to(other)
    r = _run_check(tmp_path, home)
    assert f"points at {other}" in r.stdout and "friday nodes --setup laptop" in r.stdout
    assert r.returncode == 1


def test_shim_is_recognised_and_refuses_foreign_shim_lookalike(tmp_path):
    assert run(tmp_path, "install").returncode == 0
    assert run(tmp_path, "install").returncode == 0
    f = tmp_path / "bin" / "friday"
    f.write_text("#!/bin/sh\necho mine\n")
    assert run(tmp_path, "install").returncode == 1 and "mine" in f.read_text()
    assert run(tmp_path, "uninstall").returncode == 1 and f.exists()


def test_launcher_prefers_recorded_path(tmp_path):
    home = tmp_path / "h"
    (home / ".local" / "state" / "friday").mkdir(parents=True)
    fake = tmp_path / "fakepy"
    fake.write_text('#!/bin/sh\necho fake "$@"\n')
    fake.chmod(0o755)
    (home / ".local" / "state" / "friday" / "python").write_text(f"{fake}\n")
    r = subprocess.run([str(FRIDAY.parent / "friday-python"), "x"], capture_output=True, text=True,
                       env={"HOME": str(home), "PATH": "/usr/bin:/bin"})
    assert r.stdout == "fake x\n" and r.stderr == ""
