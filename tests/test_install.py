"""friday install / uninstall against a temp bin dir."""
import os
import subprocess
import sys
from pathlib import Path

FRIDAY = Path(__file__).resolve().parent.parent / "bin" / "friday"


def run(tmp_path, *args, path=""):
    env = {**os.environ, "HOME": str(tmp_path / "home"), "PATH": path or os.environ["PATH"]}
    return subprocess.run([sys.executable, str(FRIDAY), *args, "--bin-dir", str(tmp_path / "bin")],
                          capture_output=True, text=True, env=env)


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
    assert link.is_symlink() and link.resolve() == FRIDAY.resolve()
    r = run(tmp_path, "install")
    assert r.returncode == 0 and "already" in r.stdout


def test_repoint_from_other_checkout(tmp_path):
    other = fake_checkout(tmp_path, "other")
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "friday").symlink_to(other)
    r = run(tmp_path, "install")
    assert r.returncode == 0
    assert str(other) in r.stdout and str(FRIDAY.resolve()) in r.stdout
    assert (tmp_path / "bin" / "friday").resolve() == FRIDAY.resolve()


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
    r = run(tmp_path, "install", path=f"{b}:/usr/bin")
    assert "is on PATH" in r.stdout and "not on PATH" not in r.stdout


def test_uninstall(tmp_path):
    run(tmp_path, "install")
    r = run(tmp_path, "uninstall")
    assert r.returncode == 0 and "removed" in r.stdout
    assert not (tmp_path / "bin" / "friday").is_symlink()
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
