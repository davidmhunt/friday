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
    assert "`uv python install 3.12`" in r.stdout and "`friday install`" in r.stdout


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
