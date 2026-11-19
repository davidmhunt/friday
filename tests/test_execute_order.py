"""exec-02: the execute workflow starts (merges Base) before it parses, so a directive added or
amended on Base is seen."""
import json
import re
from pathlib import Path

import subprocess

from test_friday import cli, _git, _two, _mk, GOOD_D, GOOD_G  # noqa: F401

SRC = (Path(__file__).resolve().parent.parent / "workflows" / "execute.js").read_text()


# ---------------------------------------------------------------- workflow source
def test_start_prompt_precedes_parse_prompt():
    start = SRC.index("friday start ${id} --no-gate")
    parse = SRC.index("friday parse ${id} --json")
    assert start < parse
    assert SRC.index("label: `start ${id}`") < parse


def test_parse_prompt_interpolates_start_sha():
    assert "const sha = String(st.sha" in SRC
    m = re.search(r"`Run \\`friday parse \$\{id\} --json\\`[^`]*`", SRC)
    assert m and "${sha}" in m.group(0)
    assert "git rev-parse HEAD" in SRC[:SRC.index("friday parse ${id} --json")]


def test_parse_failure_runs_finish_blocked():
    tail = SRC[SRC.index("friday parse ${id} --json"):SRC.index("phase('Implement')")]
    assert "block(`parse failed:" in tail and "block('the parse step returned nothing')" in tail
    helper = SRC[SRC.index("async function block"):SRC.index("// Every reported gap")]
    assert "friday finish ${id}" in helper and '--blocked "' in helper


# ---------------------------------------------------------------- CLI
def _amend_on_main(repo, rel, text):
    _git(repo, "switch", "-q", "main")
    p = repo / rel
    p.write_text(text(p) if callable(text) else text)
    _git(repo, "add", rel)
    _git(repo, "commit", "--no-verify", "-qm", f"base: {rel}")
    _git(repo, "switch", "-q", "friday/core")


def _parse(repo, did):
    r = cli(repo, "parse", did, "--json")
    return r.returncode, (json.loads(r.stdout) if r.stdout.strip() else {})


def test_start_makes_base_only_directive_parseable_and_amendment_visible(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    grepo2 = tmp_path / "g"
    grepo2.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(grepo2)], check=True)
    for k, v in (("user.name", "t"), ("user.email", "t@t")):
        _git(grepo2, "config", k, v)
    ds, g = _two("approved", "approved")
    _mk(grepo2, ds, g)
    _git(grepo2, "add", ".")
    _git(grepo2, "commit", "--no-verify", "-qm", "init")
    assert cli(grepo2, "start", "core-01").returncode == 0
    # committed only on Base: absent from the goal branch until start merges Base
    side_d = GOOD_D.replace("core-01", "side-01").replace("Goal: core", "Goal: side")
    side_g = GOOD_G.replace("# core:", "# side:").replace("core-01", "side-01")
    _amend_on_main(grepo2, "docs/goals/side.md", side_g)
    _amend_on_main(grepo2, "docs/directives/side-01.md", side_d)
    code, _ = _parse(grepo2, "side-01")
    assert code != 0
    _amend_on_main(grepo2, "docs/directives/core-01.md",
                   lambda p: p.read_text().replace("1. ", "1. AMENDED ", 1))
    _, before = _parse(grepo2, "core-01")
    assert not any("AMENDED" in s["text"] for s in before["steps"])
    r = cli(grepo2, "start", "core-01")
    assert r.returncode == 0, r.stderr
    code, d = _parse(grepo2, "side-01")
    assert code == 0 and not d.get("errors"), d
    _, after = _parse(grepo2, "core-01")
    assert any("AMENDED" in s["text"] for s in after["steps"])
