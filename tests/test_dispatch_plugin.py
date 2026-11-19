"""The node probe reports whether friday@ is installed and from where; launch_line drops
--plugin-dir only when it is installed from the node's plugin_dir. The remote probe runs locally
here with a fake `claude`. Run: uv run --with pytest pytest -q tests/test_dispatch_plugin.py"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
import friday_fleet as ff  # noqa: E402


def probe(tmp_path, plugins, plugin_dir):
    """Run the probe lines under a fake `claude plugin list --json`; returns (state, dir)."""
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    claude = bindir / "claude"
    claude.write_text(f"#!/bin/bash\ncat <<'EOF'\n{json.dumps(plugins)}\nEOF\n")
    claude.chmod(0o755)
    node = ff.Node("w", "worker", "me@w", repos="~/r", plugin_dir=str(plugin_dir))
    env = dict(os.environ, PATH=f"{bindir}:{os.environ['PATH']}")
    r = subprocess.run(["bash"], input=ff.plugin_install_lines(node) + "\n", env=env,
                       capture_output=True, text=True)
    return ff.parse_plugin_install(r.stdout)


def entry(folder, enabled=True):
    return {"id": "friday@friday", "enabled": enabled, "readFromFolder": str(folder),
            "installPath": "/cache/friday"}


def test_installed_from_plugin_dir(tmp_path):
    pd = tmp_path / "friday"
    pd.mkdir()
    assert probe(tmp_path, [entry(pd)], pd) == ("same", str(pd))


def test_not_installed_or_disabled(tmp_path):
    pd = tmp_path / "friday"
    pd.mkdir()
    other = {"id": "github@synced", "enabled": True}
    assert probe(tmp_path, [other], pd)[0] == "none"
    assert probe(tmp_path, [entry(pd, enabled=False)], pd)[0] == "disabled"


def test_installed_elsewhere(tmp_path):
    pd, other = tmp_path / "friday", tmp_path / "copy"
    pd.mkdir()
    other.mkdir()
    assert probe(tmp_path, [entry(other)], pd) == ("other", str(other))


@pytest.mark.parametrize("state,has_flag", [("same", False), ("none", True), ("other", True),
                                            ("disabled", True), ("unknown", True), ("", True)])
def test_launch_line_plugin_dir(state, has_flag):
    node = ff.Node("w", "worker", "me@w", repos="~/r", plugin_dir="/opt/friday")
    line = ff.launch_line(node, "g1", "/w/g1", "laptop", ["g1-01"], "boss", state)
    assert ("--plugin-dir /opt/friday" in line) is has_flag


def run_check(tmp_path, monkeypatch, settings, plugins=None):
    """check_node against a fake ssh that runs the probe script locally with a fake HOME."""
    import importlib.machinery, importlib.util
    loader = importlib.machinery.SourceFileLoader(
        "friday_cli", str(Path(__file__).resolve().parent.parent / "bin" / "friday"))
    spec = importlib.util.spec_from_loader("friday_cli", loader)
    cli = importlib.util.module_from_spec(spec)
    loader.exec_module(cli)
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True, exist_ok=True)
    (home / ".claude" / "settings.json").write_text(json.dumps(settings))
    node = ff.Node("w", "worker", "me@w", repos=str(tmp_path / "r"), plugin_dir=str(tmp_path / "pd"))
    script = cli.probe_script(node)
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    (bindir / "claude").write_text("#!/bin/bash\n[ \"$1\" = --version ] && echo '2.1.0 (Claude Code)' && exit 0\n"
                                   f"cat <<'EOF'\n{json.dumps(plugins or [])}\nEOF\n")
    (bindir / "claude").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bindir}:{os.environ['PATH']}")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(cli.ff, "ssh_cmd", lambda n, s: (["bash"], s))
    return cli.check_node(node)


def test_nodes_check_prints_outside_reads_and_install(tmp_path, monkeypatch):
    summary, fixes = run_check(tmp_path, monkeypatch, {})
    assert "outside-reads ok" in summary and "plugin install none" in summary
    assert not [f for f in fixes if "outside the working directories" in f]


def test_nodes_check_warns_when_reads_blocked(tmp_path, monkeypatch):
    summary, fixes = run_check(tmp_path, monkeypatch,
                               {"permissions": {"blockReadsOutsideWorkingDirectories": True}})
    assert "outside-reads prompts" in summary
    w = [f for f in fixes if "outside the working directories" in f]
    assert len(w) == 1 and w[0].startswith("warning:")
    assert "permissions.blockReadsOutsideWorkingDirectories" in w[0]


def test_nodes_check_plugin_install_states(tmp_path, monkeypatch):
    pd, other = tmp_path / "pd", tmp_path / "copy"
    pd.mkdir()
    other.mkdir()
    summary, fixes = run_check(tmp_path, monkeypatch, {}, [entry(pd)])
    assert "plugin install same" in summary
    assert not [f for f in fixes if "two copies" in f]
    summary, fixes = run_check(tmp_path, monkeypatch, {}, [entry(other)])
    assert "plugin install other" in summary
    w = [f for f in fixes if "two copies" in f]
    assert len(w) == 1 and w[0].startswith("warning:")
