"""The /friday:* slash-command skills: frontmatter, real CLI commands, dry-run-then-ask order."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRIDAY = ROOT / "bin" / "friday"
NAMES = ["status", "nodes", "dispatch", "clean"]
ARGUMENT = {"dispatch", "clean"}  # take an argument, so need argument-hint


def frontmatter(name):
    text = (ROOT / "skills" / name / "SKILL.md").read_text()
    m = re.match(r"---\n(.*?)\n---\n(.*)", text, re.S)
    assert m, f"{name}: no frontmatter"
    fm = dict(line.split(": ", 1) for line in m.group(1).splitlines())
    return fm, m.group(2)


def parser_flags():
    """{subcommand: set of flags} read from the add_parser/add_argument calls in bin/friday."""
    out, cur = {}, None
    for line in FRIDAY.read_text().splitlines():
        for m in re.finditer(r'sub\.add_parser\("(\w+)"\)', line):
            cur = out.setdefault(m.group(1), set())
        if cur is not None:
            cur.update(re.findall(r'add_argument\("(--[\w-]+)"', line))
    return out


def friday_commands(body):
    """Every `friday ...` invocation in a body, as (subcommand, flags)."""
    cmds = []
    for m in re.finditer(r"(?:^|`)friday ([^`\n]+)", body, re.M):
        words = m.group(1).split()
        cmds.append((words[0], [w for w in words[1:] if w.startswith("--")]))
    return cmds


def test_skills_parse():
    for n in NAMES:
        fm, body = frontmatter(n)
        assert fm["name"] == n
        assert "user-invoked" in fm["description"].lower()
        assert fm["disable-model-invocation"] == "true"
        assert ("argument-hint" in fm) or n not in ARGUMENT
        assert "run friday install" in body


def test_commands_exist_in_parser():
    flags = parser_flags()
    for n in NAMES:
        _, body = frontmatter(n)
        cmds = friday_commands(body)
        assert cmds, n
        for sub, fl in cmds:
            assert sub in flags, f"{n}: unknown command {sub}"
            for f in fl:
                assert f in flags[sub], f"{n}: {sub} has no {f}"


def test_dispatch_and_clean_dry_run_then_ask():
    for n in ("dispatch", "clean"):
        _, body = frontmatter(n)
        dry = body.index("--dry-run")
        ask = body.lower().index("ask the user")
        real = [m.start() for m in re.finditer(r"(?:^|`)friday [^`\n]*", body, re.M)
                if "--dry-run" not in m.group(0)]
        assert real, n
        assert dry < ask < real[0], n
