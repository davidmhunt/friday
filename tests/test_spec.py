"""docs/spec.md is the single reference: it must name everything the code defines, and no doc may
mention a `friday <sub>` or flag the parser lacks."""
import argparse
import importlib.machinery
import importlib.util
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib"))
sys.path.insert(0, str(ROOT / "hooks"))
import friday_core as fc  # noqa: E402
import friday_hook as fh  # noqa: E402

SPEC = (ROOT / "docs" / "spec.md").read_text()

# One label per fh.DENY rule, in order; the spec's deny-list table uses these labels.
DENY_LABELS = ["sudo", "chmod " + "777", "rm -rf", "force-push", "+refspec", "push to main", "push to friday-plan", "git remote add",
               "git clean -f", "curl pipe sh", "eval fetched", "raw disk write"]


def _load_friday():
    loader = importlib.machinery.SourceFileLoader("friday_cli", str(ROOT / "bin" / "friday"))
    spec = importlib.util.spec_from_loader("friday_cli", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def _parser():
    """The real parser: run main() with parse_args intercepted."""
    mod = _load_friday()
    got = {}
    orig = argparse.ArgumentParser.parse_args

    def grab(self, *a, **k):
        got["p"] = self
        raise SystemExit(0)

    argparse.ArgumentParser.parse_args = grab
    try:
        with pytest.raises(SystemExit):
            mod.main()
    finally:
        argparse.ArgumentParser.parse_args = orig
    return got["p"]


def _commands():
    """{subcommand: set of option strings}"""
    p = _parser()
    sp = next(a for a in p._actions if isinstance(a, argparse._SubParsersAction))
    return {n: {o for a in s._actions for o in a.option_strings if o.startswith("--") and o != "--help"}
            for n, s in sp.choices.items()}


def _has(token):
    return re.search(rf"(?<![\w-]){re.escape(token)}(?![\w-])", SPEC) is not None


def test_extraction_finds_things():
    cmds = _commands()
    assert {"status", "land", "dispatch", "nodes", "result", "dash"} <= set(cmds)
    assert "--goal" in cmds["land"] and "--resume" in cmds["dispatch"]
    assert len(fh.DENY) == len(DENY_LABELS)


def test_every_subcommand_and_option_in_spec():
    missing = []
    for sub, opts in _commands().items():
        if not re.search(rf"friday {re.escape(sub)}\b", SPEC):
            missing.append(f"friday {sub}")
        missing += [f"{sub} {o}" for o in sorted(opts) if not _has(o)]
    assert not missing, f"not in docs/spec.md: {missing}"


def test_every_header_key_section_and_value_in_spec():
    tokens = (set(fc.HEADER_KEYS) | set(fc.DIRECTIVE_KEYS) | set(fc.GOAL_KEYS) | set(fc.ACCEPTS)
              | set(fc.DELIVERABLES) | set(fc.DIRECTIVE_LANDS) | set(fc.GOAL_LANDS))
    missing = [t for t in sorted(tokens) if not _has(t)]
    for s in sorted(set(fc.DIRECTIVE_SECTIONS) | set(fc.GOAL_SECTIONS) | {"Acceptance", "Review", "Allowed commands"}):
        if f"## {s}" not in SPEC:
            missing.append(f"## {s}")
    for st in ("proposed", "approved", "running", "awaiting review", "done", "blocked"):
        if not _has(st):
            missing.append(st)
    assert not missing, f"not in docs/spec.md: {missing}"


def test_exit_codes_in_spec():
    import friday_fleet as ff
    mod = _load_friday()
    rows = dict((c, k) for c, k in re.findall(r"^\| (\d+) \| (\S+) \|", SPEC, re.M))  # exit -> kind
    missing = []
    for kind, code in {**mod.DISPATCH_EXIT, **ff.PREPARE_EXIT}.items():
        if rows.get(str(code)) != kind:
            missing.append(f"dispatch {code} {kind}")
    land = next(l for l in SPEC.splitlines() if l.startswith("| `friday land "))
    for code in (0, 3, 4, 5, 6, 7):
        if not re.search(rf"(?<![\w-]){code}(?![\w-])", land):
            missing.append(f"land {code}")
    assert not missing, f"exit codes missing or mislabelled in docs/spec.md: {missing}"


def test_deny_labels_in_spec():
    block = SPEC[SPEC.index("| Label | Refuses |"):]
    labels = re.findall(r"^\| `([^`]+)` \|", block.split("\n\n")[0], re.M)
    assert labels == DENY_LABELS, "spec deny-list table and DENY_LABELS differ"


def test_hook_rules_in_spec():
    for rule in ("Deny list", "`friday accept` guard", "`run_only`", "Push guard", "Commit guard",
                 "Pre-approval", "Hardware", "commit-msg", "--no-verify"):
        assert rule in SPEC, rule


# ---- no doc mentions a `friday <sub>` or flag the parser lacks
def _docs():
    paths = [ROOT / "README.md"] + sorted((ROOT / "docs").glob("*.md")) + sorted((ROOT / "skills").rglob("*.md")) \
        + sorted((ROOT / "agents").glob("*.md"))
    return [p for p in paths if p.name != "HANDOFF.md"]


def _mentions(text):
    """(sub, [flags]) for each `friday <sub> ...` at the start of an inline code span or fenced code line (or after a path such as `bin/`)."""
    spans = re.findall(r"`([^`\n]+)`", text)
    for block in re.findall(r"```[^\n]*\n(.*?)```", text, re.S):
        spans += block.splitlines()
    for sp in spans:
        sp = sp.split(" #")[0]   # a trailing shell comment is prose
        for m in re.finditer(r"(?:^|[/])friday ([a-z][a-z-]*)((?:\s+[^\s`|;&]+)*)", sp):
            yield m.group(1), re.findall(r"(?<![\w-])(--[a-z][a-z-]*)", m.group(2))


def test_docs_name_only_real_commands_and_flags():
    cmds = _commands()
    bad = []
    for p in _docs():
        for sub, flags in _mentions(p.read_text()):
            if sub not in cmds:
                bad.append(f"{p.relative_to(ROOT)}: friday {sub}")
                continue
            bad += [f"{p.relative_to(ROOT)}: friday {sub} {f}" for f in flags if f not in cmds[sub] and f != "--help"]
    assert not bad, f"docs name commands or flags the parser lacks: {sorted(set(bad))}"
