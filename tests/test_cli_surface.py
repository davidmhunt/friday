"""CLI surface: --help lists every subcommand and option the parser accepts; every `friday <sub>` that
skills and the execute workflow run matches an allow rule (or is a user-invoked command that asks)."""
import argparse
import fnmatch
import importlib.machinery
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRIDAY = ROOT / "bin" / "friday"
sys.path.insert(0, str(ROOT / "lib"))
import friday_core as fc  # noqa: E402

PROMPTED = ("dispatch --goal *", "nodes --clean *", "release *")


def prompted():
    """The commands that stay prompted on purpose, not in FRIDAY_ALLOW (they act on other machines or
    free hardware; amended by the user 2026-11-18): `dispatch --goal <g>`, `nodes --clean <node>` and
    `release <resource>`. Their dry-runs are allowed by their own rules."""
    return PROMPTED


def is_prompted(inv):
    return any(fnmatch.fnmatchcase(inv, pat) for pat in prompted()) and not allowed(inv)


def build_parser():
    """The real parser: run main() with parse_args intercepted."""
    loader = importlib.machinery.SourceFileLoader("friday_cli_surface", str(FRIDAY))
    spec = importlib.util.spec_from_loader("friday_cli_surface", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    got = {}

    class Stop(Exception):
        pass

    def grab(self, *a, **k):
        got["p"] = self
        raise Stop

    orig = argparse.ArgumentParser.parse_args
    argparse.ArgumentParser.parse_args = grab
    try:
        try:
            mod.main()
        except Stop:
            pass
    finally:
        argparse.ArgumentParser.parse_args = orig
    return got["p"]


def help_text():
    r = subprocess.run([sys.executable, str(FRIDAY), "--help"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout


def test_help_lists_every_subcommand_and_option():
    p = build_parser()
    (sp,) = [a for a in p._actions if isinstance(a, argparse._SubParsersAction)]
    text = help_text()
    assert len(sp.choices) >= 15
    for name, sub in sp.choices.items():
        assert re.search(rf"^\s*friday {re.escape(name)}\b", text, re.M), f"subcommand {name} not in --help"
        for act in sub._actions:
            for opt in act.option_strings:
                if opt in ("-h", "--help"):
                    continue
                assert opt in text, f"{name} {opt} not in --help"


def allowed(cmd):
    """Does `friday <cmd>` match a Bash(friday ...) rule? A trailing ` *` matches any arguments."""
    for rule in fc.FRIDAY_ALLOW:
        pat = rule[len("Bash(friday "):-1]
        if "*" in pat[:-1]:
            if fnmatch.fnmatchcase(cmd, pat):
                return True
        elif pat.endswith(" *"):
            base = pat[:-2]
            if cmd == base or cmd.startswith(base + " "):
                return True
        elif cmd == pat:
            return True
    return False


def invocations(text):
    """`friday ...` inside backtick spans or on a line of its own (JS escapes \\` unwrapped)."""
    text = text.replace("\\`", "`")
    out = [m.group(1).strip() for m in re.finditer(r"`friday ([^`\n]+)`", text)]
    out += [m.group(1).strip() for m in re.finditer(r"^friday ([^\n`]+)$", text, re.M)]
    return out


def sources():
    for f in sorted((ROOT / "skills").glob("*/SKILL.md")):
        yield f.relative_to(ROOT), f.read_text()
    yield Path("workflows/execute.js"), (ROOT / "workflows" / "execute.js").read_text()


def test_skill_and_workflow_commands_match_allow_rules():
    p = build_parser()
    (sp,) = [a for a in p._actions if isinstance(a, argparse._SubParsersAction)]
    seen = 0
    for path, text in sources():
        for inv in invocations(text):
            sub = inv.split()[0]
            if sub not in sp.choices:  # prose such as `friday` alone or a placeholder
                continue
            seen += 1
            assert allowed(inv) or is_prompted(inv), f"{path}: `friday {inv}` matches no allow rule"
    assert seen >= 10
    for ok in ("nodes", "nodes --check", "nodes --clean n1 --dry-run", "dispatch --goal g --dry-run"):
        assert allowed(ok), ok
    for held in ("nodes --clean n1", "dispatch --goal g", "release r1"):
        assert not allowed(held) and is_prompted(held), held


def test_workflow_commands_all_match_allow_rules():
    text = (ROOT / "workflows" / "execute.js").read_text()
    subs = {i.split()[0] for i in invocations(text)}
    assert {"parse", "start", "finish", "land"} <= subs
    for inv in invocations(text):
        assert allowed(inv), f"execute.js: `friday {inv}`"


def test_allow_rules_match_settings_and_exclude_accept():
    rules = json.loads((ROOT / ".claude" / "settings.json").read_text())["permissions"]["allow"]
    assert rules == fc.FRIDAY_ALLOW
    assert "Bash(friday init)" in rules and "Bash(friday session-end *)" in rules
    assert not any("accept" in r for r in rules)


# ---- step 1: status --node
def test_status_node_is_a_documented_flag_and_names_the_snapshot(tmp_path):
    assert "friday status --node NAME" in help_text()
    repo = tmp_path / "r"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    env = {**os.environ, "HOME": str(tmp_path), "FRIDAY_NODES": str(tmp_path / "none.toml")}
    r = subprocess.run([sys.executable, str(FRIDAY), "status", "--json", "--node", "boxy"],
                       cwd=repo, capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["node"] == "boxy"


# ---- step 2: nodes --check counts friday-* sessions
def test_nodes_check_probe_counts_friday_sessions():
    src = FRIDAY.read_text()
    assert "FRIDAY_PROBE sessions=" in src and "grep -c '^friday-'" in src
    assert "friday-* sessions" in src


# ---- step 5: tailnet key and the resolved registry mount
def test_tailnet_key_documented():
    assert re.search(r"^#?\s*tailnet\s*=", (ROOT / "nodes.example.toml").read_text(), re.M)
    assert "`tailnet`" in (ROOT / "docs" / "fleet.md").read_text()


def test_dash_up_without_registry_fails_clearly(tmp_path):
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    d = bin_ / "docker"
    d.write_text("#!/bin/sh\nexit 0\n")
    d.chmod(0o755)
    env = {k: v for k, v in os.environ.items() if k != "FRIDAY_NODES"}
    env.update(HOME=str(tmp_path), PATH=f"{bin_}{os.pathsep}{os.path.dirname(sys.executable)}")
    if (ROOT / "nodes.toml").exists():
        return  # a plugin-root registry would be found; nothing to assert
    r = subprocess.run([sys.executable, str(FRIDAY), "dash", "up"], env=env, capture_output=True, text=True)
    assert r.returncode != 0 and "no registry file found" in r.stderr


def test_no_unquoted_tmux_equals_target():
    """zsh expands a bare `=word`, so every `-t =...` friday prints or builds must be quoted."""
    bad = []
    for p in [*(ROOT / "bin").glob("*"), *(ROOT / "lib").glob("*")]:
        if not p.is_file():
            continue
        for n, line in enumerate(p.read_text(errors="replace").splitlines(), 1):
            if re.search(r"-t\s+=", line):
                bad.append(f"{p.relative_to(ROOT)}:{n}: {line.strip()}")
    assert not bad, "unquoted tmux target:\n" + "\n".join(bad)


def test_resume_kill_line_runs_under_zsh(tmp_path):
    import shutil
    zsh = shutil.which("zsh")
    if not zsh:
        import pytest
        pytest.skip("zsh not installed")
    m = re.search(r'^\s*kill = (f".*")$', FRIDAY.read_text(), re.M)
    assert m, "dispatch --resume kill line not found in bin/friday"
    gid = "g1"
    kill = eval(m.group(1), {"gid": gid})
    fake = tmp_path / "tmux"
    fake.write_text('#!/bin/sh\nfor a; do echo "ARG:$a"; done\n')
    fake.chmod(0o755)
    r = subprocess.run([zsh, "-c", kill], capture_output=True, text=True,
                       env={**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}"})
    assert r.returncode == 0, r.stderr
    assert r.stdout.split() == ["ARG:kill-session", "ARG:-t", "ARG:=friday-g1"]
