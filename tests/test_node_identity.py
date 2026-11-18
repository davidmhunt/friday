import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
import friday_status as fs  # noqa: E402


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
