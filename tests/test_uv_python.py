"""tt-09: probe script, 3.10-only node report, tomli fallback."""
import importlib.machinery
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRIDAY = ROOT / "bin" / "friday"


def _load_cli():
    sys.path.insert(0, str(ROOT / "lib"))
    loader = importlib.machinery.SourceFileLoader("friday_cli_under_test", str(FRIDAY))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def _node(mod, role="master"):
    import friday_fleet as ff
    return ff.Node(name="n", role=role, ssh="me@n", repos="~/r", plugin_dir="~/p") if hasattr(ff, "Node") else None


def test_probe_script_has_no_bare_python3():
    cli = _load_cli()
    node = _node(cli)
    assert node is not None
    script = cli.probe_script(node, prereqs=True)
    assert "python3 -c" not in script and "python3" not in script.replace("system python3", "")
    assert "friday-python" in script


def test_check_reports_310_only_node(tmp_path):
    home = tmp_path / "home"
    (home / ".local" / "state" / "friday").mkdir(parents=True)
    py = tmp_path / "py310"
    py.write_text("#!/bin/sh\necho '(3, 10)'\n")
    py.chmod(0o755)
    (home / ".local" / "state" / "friday" / "python").write_text(f"{py}\n")
    (tmp_path / "n.toml").write_text(
        f'[node.old]\nrole = "master"\nssh = "me@old"\nrepos = "~/r"\nplugin_dir = "{ROOT}"\n')
    ssh = tmp_path / "fakessh"
    ssh.write_text("#!/bin/bash\nexec bash -s\n")
    ssh.chmod(0o755)
    env = {**os.environ, "HOME": str(home), "FRIDAY_NODES": str(tmp_path / "n.toml"),
           "FRIDAY_SSH": str(ssh), "PATH": "/usr/bin:/bin"}
    r = subprocess.run([sys.executable, str(FRIDAY), "nodes", "--check"],
                       capture_output=True, text=True, env=env)
    assert r.returncode == 1
    assert "python (3, 10)" in r.stdout
    assert "friday needs 3.11+" in r.stdout
    assert "`friday install`" in r.stdout and "uv python install" not in r.stdout


def test_imports_under_tomli_fallback(tmp_path):
    stub = tmp_path / "stub"
    stub.mkdir()
    (stub / "tomli.py").write_text("class TOMLDecodeError(ValueError): pass\ndef loads(s): return {}\n"
                                   "def load(f): return {}\nMARK = 1\n")
    code = ("import sys; sys.modules['tomllib'] = None; sys.path.insert(0, %r); sys.path.insert(0, %r)\n"
            "import friday_fleet, friday_core\n"
            "assert friday_fleet.tomllib.MARK == 1\nprint('ok')\n" % (str(stub), str(ROOT / "lib")))
    r = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True)
    assert r.stdout.strip() == "ok", r.stderr
    r = subprocess.run([sys.executable, "-c",
                        "import sys; sys.modules['tomllib'] = None; sys.path.insert(0, %r); sys.path.insert(0, %r)\n"
                        "import runpy; sys.argv=['friday','--help']\n"
                        "try: runpy.run_path(%r, run_name='__main__')\nexcept SystemExit as e: print('exit', e.code)\n"
                        % (str(stub), str(ROOT / "lib"), str(FRIDAY))],
                       capture_output=True, text=True)
    assert "exit 0" in r.stdout, r.stdout + r.stderr


def test_cli_imports_with_no_toml_parser():
    """Stock 3.10 has neither tomllib nor tomli; `friday install` must still be able to start."""
    code = ("import sys; sys.modules['tomllib'] = None; sys.modules['tomli'] = None; sys.path.insert(0, %r)\n"
            "import runpy; sys.argv=['friday','--help']\n"
            "try: runpy.run_path(%r, run_name='__main__')\nexcept SystemExit as e: print('exit', e.code)\n"
            % (str(ROOT / "lib"), str(FRIDAY)))
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert "exit 0" in r.stdout, r.stdout + r.stderr


def test_status_warns_without_recorded_python(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    env = {**os.environ, "HOME": str(home)}
    r = subprocess.run([sys.executable, str(FRIDAY), "status"], capture_output=True, text=True, env=env, cwd=repo)
    assert "no friday Python is recorded" in r.stderr and "friday install" in r.stderr, r.stdout + r.stderr
    rec = home / ".local" / "state" / "friday"
    rec.mkdir(parents=True, exist_ok=True)
    (rec / "python").write_text(f"{sys.executable}\n")
    r = subprocess.run([sys.executable, str(FRIDAY), "status"], capture_output=True, text=True, env=env, cwd=repo)
    assert "no friday Python is recorded" not in r.stderr, r.stderr


def _logging_uv(tmp_path, found):
    """A fake uv that logs its args and UV_PYTHON_INSTALL_DIR, and prints `found` for `python find`."""
    d = tmp_path / "fakeuv"
    d.mkdir(exist_ok=True)
    log = tmp_path / "uv.log"
    uv = d / "uv"
    uv.write_text(f'#!/bin/sh\necho "$* | dir=$UV_PYTHON_INSTALL_DIR" >> {log}\n'
                  f'[ "$2" = find ] && echo "{found}"\nexit 0\n')
    uv.chmod(0o755)
    return d, log


def _install_env(tmp_path, found):
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    d, log = _logging_uv(tmp_path, found)
    env = {**os.environ, "HOME": str(home), "PATH": f"{d}:{os.environ['PATH']}"}
    env.pop("XDG_DATA_HOME", None)
    return env, log, home / ".local" / "share" / "friday" / "python"


def _py_in(pdir):
    py = pdir / "cpython-3.12" / "bin" / "python3.12"
    py.parent.mkdir(parents=True, exist_ok=True)
    py.write_text("#!/bin/sh\n")
    py.chmod(0o755)
    return py


def test_install_private_dir_flags_and_only_shim_in_bin(tmp_path):
    env, log, pdir = _install_env(tmp_path, "")
    py = _py_in(pdir)
    (tmp_path / "uv.log").write_text("")
    env, log, pdir = _install_env(tmp_path, str(py))
    bindir = tmp_path / "bin"
    r = subprocess.run([sys.executable, str(FRIDAY), "install", "--bin-dir", str(bindir)],
                       capture_output=True, text=True, env=env, cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    lines = log.read_text().splitlines()
    inst = next(x for x in lines if x.startswith("python install"))
    assert "--no-bin" in inst and f"--install-dir {pdir}" in inst and f"dir={pdir}" in inst
    find = next(x for x in lines if x.startswith("python find"))
    assert "--managed-python" in find and f"dir={pdir}" in find
    assert [p.name for p in bindir.iterdir()] == ["friday"]


def test_install_refuses_path_outside_private_dir(tmp_path):
    outside = tmp_path / "elsewhere" / "python3.12"
    outside.parent.mkdir()
    outside.write_text("#!/bin/sh\n")
    outside.chmod(0o755)
    env, log, pdir = _install_env(tmp_path, str(outside))
    bindir = tmp_path / "bin"
    r = subprocess.run([sys.executable, str(FRIDAY), "install", "--bin-dir", str(bindir)],
                       capture_output=True, text=True, env=env, cwd=tmp_path)
    assert r.returncode == 1 and "outside" in r.stderr
    assert not (tmp_path / "home" / ".local" / "state" / "friday" / "python").exists()
    assert not (bindir / "friday").exists()


def test_uninstall_removes_private_dir(tmp_path):
    env, log, pdir = _install_env(tmp_path, "")
    py = _py_in(pdir)
    env, log, pdir = _install_env(tmp_path, str(py))
    bindir = tmp_path / "bin"
    args = [sys.executable, str(FRIDAY), "{}", "--bin-dir", str(bindir)]
    r = subprocess.run([a if a != "{}" else "install" for a in args], capture_output=True, text=True, env=env, cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert pdir.exists()
    r = subprocess.run([a if a != "{}" else "uninstall" for a in args], capture_output=True, text=True, env=env, cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert not pdir.exists() and not (bindir / "friday").exists()


def test_launcher_uv_fallback_uses_private_dir_and_managed_python(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    fake = tmp_path / "bin"
    fake.mkdir()
    shutil_head = subprocess.run(["which", "head"], capture_output=True, text=True).stdout.strip()
    (fake / "head").symlink_to(shutil_head)
    py = fake / "mypy"
    py.write_text('#!/bin/sh\necho "uvpy $*"\n')
    py.chmod(0o755)
    log = tmp_path / "uv.log"
    uv = fake / "uv"
    uv.write_text(f'#!/bin/sh\necho "$* | dir=$UV_PYTHON_INSTALL_DIR" >> {log}\necho {py}\n')
    uv.chmod(0o755)
    r = subprocess.run(["/bin/sh", str(ROOT / "bin" / "friday-python"), "a"],
                       env={"HOME": str(home), "PATH": str(fake)}, capture_output=True, text=True)
    assert r.stdout.strip() == "uvpy a", r.stderr
    pdir = home / ".local" / "share" / "friday" / "python"
    assert log.read_text().strip() == f"python find --managed-python 3.12 | dir={pdir}"


def test_launcher_uv_fallback_ignores_active_virtualenv(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    fake = tmp_path / "bin"
    fake.mkdir()
    (fake / "head").symlink_to(subprocess.run(["which", "head"], capture_output=True, text=True).stdout.strip())
    py = fake / "mypy"
    py.write_text('#!/bin/sh\necho "uvpy $*"\n')
    py.chmod(0o755)
    log = tmp_path / "uv.log"
    uv = fake / "uv"
    uv.write_text(f'#!/bin/sh\necho "venv=[$VIRTUAL_ENV]" >> {log}\necho {py}\n')
    uv.chmod(0o755)
    r = subprocess.run(["/bin/sh", str(ROOT / "bin" / "friday-python"), "a"],
                       env={"HOME": str(home), "PATH": str(fake), "VIRTUAL_ENV": "/some/venv"},
                       capture_output=True, text=True)
    assert r.stdout.strip() == "uvpy a", r.stderr
    assert log.read_text().strip() == "venv=[]"


def test_uv_python_does_not_pass_virtualenv_to_uv(tmp_path, monkeypatch):
    fake = tmp_path / "bin"
    fake.mkdir()
    pdir = tmp_path / "data" / "friday" / "python"
    py = pdir / "py312"
    log = tmp_path / "uv.log"
    uv = fake / "uv"
    uv.write_text(f'#!/bin/sh\necho "venv=[$VIRTUAL_ENV]" >> {log}\nmkdir -p {pdir}; : > {py}\necho {py}\n')
    uv.chmod(0o755)
    monkeypatch.setenv("PATH", f"{fake}:{os.environ['PATH']}")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("VIRTUAL_ENV", "/some/venv")
    assert _load_cli()._uv_python() == str(py)
    assert set(log.read_text().split()) == {"venv=[]"}
