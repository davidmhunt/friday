import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
import friday_status as fs  # noqa: E402
import friday_fleet  # noqa: E402


def _repo(base, name):
    r = base / name
    (r / ".git").mkdir(parents=True)
    (r / "docs" / "goals").mkdir(parents=True)
    return r


def test_node_file_names_node_and_scans_repos(tmp_path, monkeypatch):
    _repo(tmp_path / "code", "proj")
    nf = tmp_path / "node.toml"
    nf.write_text(f'name = "alfred"\nrepos = "{tmp_path / "code"}"\ndash = "http://m:1"\n')
    monkeypatch.setenv("FRIDAY_NODE_FILE", str(nf))
    monkeypatch.setenv("FRIDAY_NODES", str(tmp_path / "none.toml"))
    snap = fs.collect(cwd=tmp_path, registry_path=tmp_path / "none.toml")
    assert snap["node"] == "alfred"
    assert [r["path"] for r in snap["repos"]] == [str(tmp_path / "code" / "proj")]


def test_node_flag_beats_node_file(tmp_path, monkeypatch):
    nf = tmp_path / "node.toml"
    nf.write_text('name = "alfred"\n')
    monkeypatch.setenv("FRIDAY_NODE_FILE", str(nf))
    snap = fs.collect(cwd=tmp_path, registry_path=tmp_path / "none.toml", node_name="x")
    assert snap["node"] == "x"


def test_bad_node_file_is_an_error_not_a_crash(tmp_path, monkeypatch):
    nf = tmp_path / "node.toml"
    nf.write_text("bogus = 1\n")
    monkeypatch.setenv("FRIDAY_NODE_FILE", str(nf))
    snap = fs.collect(cwd=tmp_path, registry_path=tmp_path / "none.toml")
    assert any("node.toml" in e["error"] for e in snap["errors"])


def test_registry_beats_node_file(tmp_path, monkeypatch):
    nf = tmp_path / "node.toml"
    nf.write_text('name = "fromfile"\n')
    monkeypatch.setenv("FRIDAY_NODE_FILE", str(nf))
    reg = tmp_path / "nodes.toml"
    reg.write_text('[nodes.m]\nname = "regname"\nssh = "me@h"\nrole = "master"\nrepos = "~/c"\n')
    snap = fs.collect(cwd=tmp_path, registry_path=reg, node_name="regname")
    assert snap["node"] == "regname"


def test_setup_writes_node_file(tmp_path):
    import subprocess
    home = tmp_path / "home"
    (home / "f").parent.mkdir(parents=True)
    (home / "f").symlink_to(Path(__file__).resolve().parent.parent)
    (tmp_path / "n.toml").write_text(
        '[node.m]\nrepos = "~/code"\nrole = "master"\nssh = "me@mhost"\nplugin_dir = "~/f"\n'
        '[node.w]\nrole = "worker"\nssh = "me@w"\nplugin_dir = "~/f"\nrepos = "~/code"\n')
    ssh = tmp_path / "fakessh"
    ssh.write_text('#!/bin/bash\nexec bash -s\n')
    ssh.chmod(0o755)
    ctl = tmp_path / "ctl"
    ctl.write_text("#!/bin/bash\n")
    ctl.chmod(0o755)
    import os
    env = dict(os.environ, FRIDAY_NODES=str(tmp_path / "n.toml"), FRIDAY_SSH=str(ssh), HOME=str(home),
               FRIDAY_SYSTEMCTL=str(ctl))
    env.pop("FRIDAY_NODE_FILE", None)
    r = subprocess.run([sys.executable, str(Path(__file__).resolve().parent.parent / "bin" / "friday"),
                        "nodes", "--setup", "w", "--yes"], env=env, capture_output=True, text=True, cwd=tmp_path)
    assert "node.toml" in r.stdout, r.stdout + r.stderr
    text = (home / ".config" / "friday" / "node.toml").read_text()
    assert 'name = "w"' in text and 'repos = "~/code"' in text and 'dash = "http://mhost:' in text
    import friday_fleet as ff
    assert ff.load_node_file(home / ".config" / "friday" / "node.toml")[0] == "w"
