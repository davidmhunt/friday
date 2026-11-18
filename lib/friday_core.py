"""Shared logic for friday's hooks and the `friday` CLI. Standard library only.

Concepts
- Project config: `.claude/friday.json` at the repo root (optional; without it only the
  deny list applies). Keys: run_wrapper, run_only, hardware, verify.
- Directive: `docs/directives/<id>.md`; goal: `docs/goals/<goal>.md`. Both formats are defined
  once, by parse_directive_full / parse_goal and validate_directive / validate_goal below.
  parse_directive is the older header-only reader kept for the hooks, `start` and `verify`.
- Active marker: `<git dir>/friday-active` (JSON), written by `friday start <id>`, removed by
  `friday finish`. Per worktree, never committed.
- Leases: `~/.local/state/friday/leases/<resource>.json`, one session holds a hardware
  resource at a time; stale after LEASE_TTL_S.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import socket
import subprocess
import time
from pathlib import Path
from typing import NamedTuple

LEASE_TTL_S = 4 * 3600
DIRECTIVE_DIR = Path("docs/directives")
HEADER_KEYS = ("Status", "Node", "Verify", "Hardware")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*-\d{2,}$")

# Allow rules every friday repo carries in its tracked .claude/settings.json (a plugin cannot
# grant permissions). Defined once here; `friday init` merges them, `friday dispatch` checks them.
FRIDAY_ALLOW = [
    f"Bash(friday {c})"
    for c in ("status", "status *", "new *", "check *", "parse *", "start *",
              "verify", "verify *", "finish *", "land *")
]


# ---------------------------------------------------------------- git / paths
def _git(args: list[str], cwd: Path) -> str | None:
    try:
        out = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def repo_root(cwd: Path | str) -> Path | None:
    top = _git(["rev-parse", "--show-toplevel"], Path(cwd))
    return Path(top) if top else None


def git_dir(cwd: Path | str) -> Path | None:
    d = _git(["rev-parse", "--absolute-git-dir"], Path(cwd))
    return Path(d) if d else None


def current_branch(cwd: Path | str) -> str | None:
    return _git(["symbolic-ref", "--quiet", "--short", "HEAD"], Path(cwd))


# ---------------------------------------------------------------- config
def load_config(root: Path | None) -> dict:
    if root is None:
        return {}
    p = root / ".claude" / "friday.json"
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return {}


# ---------------------------------------------------------------- directives
def directive_path(root: Path, did: str) -> Path:
    return root / DIRECTIVE_DIR / f"{did}.md"


def parse_directive(text: str) -> dict:
    """Title from the first `# ` line; header keys from `Key: value` lines before the first `## `."""
    d: dict = {"title": "", **{k.lower(): "" for k in HEADER_KEYS}}
    for line in text.splitlines():
        if line.startswith("## "):
            break
        if line.startswith("# ") and not d["title"]:
            d["title"] = line[2:].strip()
            continue
        m = re.match(r"^(Status|Node|Verify|Hardware):\s*(.*)$", line)
        if m:
            d[m.group(1).lower()] = m.group(2).strip().strip("`").strip()
    return d


def read_directive(root: Path, did: str) -> dict | None:
    p = directive_path(root, did)
    try:
        d = parse_directive(p.read_text())
    except OSError:
        return None
    d["id"] = did
    d["path"] = str(p)
    return d


def set_status(root: Path, did: str, status: str) -> None:
    p = directive_path(root, did)
    text = p.read_text()
    new, n = re.subn(r"(?m)^Status:.*$", f"Status: {status}", text, count=1)
    if n == 0:
        raise ValueError(f"{p} has no Status: line")
    p.write_text(new)


def list_directives(root: Path) -> list[dict]:
    out = []
    for p in sorted((root / DIRECTIVE_DIR).glob("*.md")):
        if p.name.upper() == "README.MD" or p.stem.upper() == "TEMPLATE":
            continue
        d = parse_directive(p.read_text())
        d["id"] = p.stem
        out.append(d)
    return out


def next_id(root: Path, loop: str) -> str:
    nums = [int(m.group(1)) for p in (root / DIRECTIVE_DIR).glob(f"{loop}-*.md")
            if (m := re.match(rf"^{re.escape(loop)}-(\d+)$", p.stem))]
    return f"{loop}-{(max(nums) + 1 if nums else 1):02d}"


# ---------------------------------------------------------------- formats: goal and directive files
# The one definition of both file formats. Parsers return the parsed shape (a dict, never raising);
# validators return a list of Issue. Errors block (`friday check` exits 1, the PostToolUse hook
# feeds them back); warnings are reported only.
GOAL_DIR = Path("docs/goals")
GOAL_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
DIRECTIVE_KEYS = ("Status", "Goal", "Node", "Deliverable", "Land", "Verify", "Hardware")
GOAL_KEYS = ("Status", "Base", "Land")
DELIVERABLES = ("code", "doc", "slides", "external")
DIRECTIVE_LANDS = ("goal", "pr", "none")
GOAL_LANDS = ("pr", "none")
DIRECTIVE_SECTIONS = ("Goal", "Steps", "Out of scope", "Log")
GOAL_SECTIONS = ("Goal", "Directives", "Log")


class Issue(NamedTuple):
    level: str      # "error" | "warning"
    path: str       # repo-relative path of the file
    line: int       # 1-based line number
    message: str

    def __str__(self) -> str:
        return f"{self.level}: {self.path}:{self.line}: {self.message}"


def goal_path(root: Path, gid: str) -> Path:
    return root / GOAL_DIR / f"{gid}.md"


def _clean(v: str) -> str:
    return v.strip().strip("`").strip()


def _parse_md(text: str) -> dict:
    """Common layer: first line (`# <name>: <title>`), header `Key: value` lines before the first
    `## `, and `## ` sections with their body lines (fenced code blocks are not scanned for `## `)."""
    lines = text.splitlines()
    out: dict = {"name": None, "title": "", "first_line": lines[0] if lines else "",
                 "headers": [], "sections": []}
    m = re.match(r"^#\s+([^\s:]+):\s*(.*)$", out["first_line"])
    if m:
        out["name"], out["title"] = m.group(1), m.group(2).strip()
    in_header, fence, cur = True, False, None
    for i, line in enumerate(lines, 1):
        if line.lstrip().startswith("```"):
            fence = not fence
        if not fence and line.startswith("## "):
            in_header = False
            cur = {"name": line[3:].strip(), "line": i, "body": []}
            out["sections"].append(cur)
            continue
        if in_header:
            if i == 1:
                continue
            h = re.match(r"^([A-Z][A-Za-z-]*):\s*(.*)$", line)
            if h:
                out["headers"].append((h.group(1), _clean(h.group(2)), i))
        elif cur is not None:
            cur["body"].append((i, line))
    return out


def _header_map(md: dict) -> dict:
    """First value of each header key."""
    hm: dict = {}
    for k, v, _ in md["headers"]:
        hm.setdefault(k, v)
    return hm


def _section(md: dict, name: str) -> dict | None:
    return next((s for s in md["sections"] if s["name"] == name), None)


def _numbered(body: list[tuple[int, str]]) -> tuple[list[dict], list[tuple[int, str]]]:
    """A numbered list `1.` .. `n.` with indented continuation lines. Returns the items
    ({n, text, line}) and the stray lines (non-blank, not an item, not indented)."""
    items: list[dict] = []
    stray: list[tuple[int, str]] = []
    for i, line in body:
        m = re.match(r"^(\d+)\.\s+(.*)$", line)
        if m:
            items.append({"n": int(m.group(1)), "line": i, "lines": [m.group(2).rstrip()]})
        elif not line.strip():
            if items:
                items[-1]["lines"].append("")
        elif line[0] in " \t" and items:
            items[-1]["lines"].append(line.strip())
        else:
            stray.append((i, line))
    for it in items:
        it["text"] = "\n".join(it.pop("lines")).strip()
    return items, stray


def _bullets(body: list[tuple[int, str]]) -> list[str]:
    out: list[str] = []
    for _, line in body:
        if line.startswith("- "):
            out.append(line[2:].strip())
        elif line.strip() and line[0] in " \t" and out:
            out[-1] += " " + line.strip()
    return out


def parse_directive_full(text: str) -> dict:
    """The parsed shape of a directive file. Keys: id, title, status, goal, node, deliverable,
    land (default `goal`), verify, hardware, steps [{n, text, heavy, line}], acceptance [str]
    (None when there is no `## Acceptance`), headers [(key, value, line)], sections [(name, line)]."""
    md = _parse_md(text)
    hm = _header_map(md)
    steps_sec = _section(md, "Steps")
    steps, _ = _numbered(steps_sec["body"]) if steps_sec else ([], [])
    for s in steps:
        # a `[heavy]` inside an inline code span is a mention of the marker, not the marker
        s["heavy"] = "[heavy]" in re.sub(r"`[^`]*`", "", s["text"])
    acc = _section(md, "Acceptance")
    return {
        "id": md["name"], "title": md["title"],
        **{k.lower(): hm.get(k, "") for k in DIRECTIVE_KEYS},
        "land": hm.get("Land", "goal") or "goal",
        "steps": [{"n": s["n"], "text": s["text"], "heavy": s["heavy"], "line": s["line"]}
                  for s in steps],
        "acceptance": _bullets(acc["body"]) if acc else None,
        "headers": md["headers"],
        "sections": [(s["name"], s["line"]) for s in md["sections"]],
    }


def parse_goal(text: str) -> dict:
    """The parsed shape of a goal file. Keys: goal, title, status, base, land, directives
    [{n, id, text, line}] (in list order), headers [(key, value, line)], sections [(name, line)]."""
    md = _parse_md(text)
    hm = _header_map(md)
    sec = _section(md, "Directives")
    items, _ = _numbered(sec["body"]) if sec else ([], [])
    dirs = []
    for it in items:
        m = re.match(r"^([^\s:]+)(.*)$", it["text"], re.S)
        did, rest = (m.group(1), m.group(2)) if m else ("", it["text"])
        dirs.append({"n": it["n"], "id": did, "text": rest.lstrip(":").strip(), "line": it["line"]})
    return {
        "goal": md["name"], "title": md["title"],
        **{k.lower(): hm.get(k, "") for k in GOAL_KEYS},
        "directives": dirs,
        "headers": md["headers"],
        "sections": [(s["name"], s["line"]) for s in md["sections"]],
    }


def _check_headers(md: dict, keys: tuple, optional: tuple, path: str, warn_unknown: bool) -> list[Issue]:
    issues: list[Issue] = []
    seen: dict[str, int] = {}
    for k, _, ln in md["headers"]:
        if k in keys:
            if k in seen:
                issues.append(Issue("error", path, ln, f"duplicate header `{k}:` (first on line {seen[k]})"))
            else:
                seen[k] = ln
        elif warn_unknown:
            issues.append(Issue("warning", path, ln, f"unknown header `{k}:`"))
    for k in keys:
        if k not in seen and k not in optional:
            issues.append(Issue("error", path, 1, f"missing header `{k}:`"))
    return issues


def _check_sections(md: dict, required: tuple, path: str, acceptance: bool) -> list[Issue]:
    """Required sections once each, in order; with `acceptance`, `## Acceptance` at most once.
    Other sections are allowed anywhere before the last required one (`## Log`)."""
    issues: list[Issue] = []
    seen: dict[str, int] = {}
    once = required + (("Acceptance",) if acceptance else ())
    last = required[-1]
    for s in md["sections"]:
        name, ln = s["name"], s["line"]
        if name in once:
            if name in seen:
                issues.append(Issue("error", path, ln, f"duplicate section `## {name}` (first on line {seen[name]})"))
                continue
            seen[name] = ln
        if last in seen and name != last:
            issues.append(Issue("error", path, ln, f"section `## {name}` comes after `## {last}`"))
    for name in required:
        if name not in seen:
            issues.append(Issue("error", path, 1, f"missing section `## {name}`"))
    order = [n for n in required if n in seen]
    for a, b in zip(order, order[1:]):
        if seen[a] > seen[b]:
            issues.append(Issue("error", path, seen[b],
                                f"section `## {b}` must come after `## {a}`"))
    return issues


def _check_numbering(items: list[dict], stray: list, sec: dict, what: str, path: str) -> list[Issue]:
    issues: list[Issue] = []
    for ln, _ in stray:
        issues.append(Issue("error", path, ln,
                            f"`## {sec['name']}`: line is not a numbered {what} or an indented continuation"))
    if not items:
        issues.append(Issue("error", path, sec["line"], f"`## {sec['name']}` has no numbered {what}s"))
    for want, it in enumerate(items, 1):
        if it["n"] != want:
            issues.append(Issue("error", path, it["line"],
                                f"`## {sec['name']}`: {what} numbered {it['n']}, expected {want}"))
            break
    return issues


def _check_title(md: dict, stem: str, kind: str, name_re: re.Pattern, path: str) -> list[Issue]:
    if md["name"] is None:
        return [Issue("error", path, 1, f"first line must be `# <{kind}>: <title>`")]
    issues: list[Issue] = []
    if md["name"] != stem:
        issues.append(Issue("error", path, 1, f"title {kind} `{md['name']}` does not match the filename `{stem}`"))
    if not name_re.match(stem):
        issues.append(Issue("error", path, 1, f"{kind} `{stem}` does not match {name_re.pattern}"))
    if not md["title"]:
        issues.append(Issue("error", path, 1, "empty title after `<" + kind + ">:`"))
    return issues


def _status_ok(status: str, running_host: bool) -> bool:
    if status in ("proposed", "approved", "done"):
        return True
    if running_host:
        if re.match(r"^running@\S+$", status):
            return True
    elif status == "running":
        return True
    return bool(re.match(r"^blocked:\s*\S", status))


def validate_directive(did: str, text: str) -> list[Issue]:
    """This one directive file's own rules (no cross-checks against goal files)."""
    path = str(DIRECTIVE_DIR / f"{did}.md")
    md = _parse_md(text)
    d = parse_directive_full(text)
    hl = {k: ln for k, _, ln in reversed(md["headers"])}   # first line of each key
    issues = _check_title(md, did, "id", ID_RE, path)
    issues += _check_headers(md, DIRECTIVE_KEYS, ("Land",), path, warn_unknown=True)

    def bad(key: str, msg: str) -> None:
        issues.append(Issue("error", path, hl.get(key, 1), msg))

    if "Status" in hl and not _status_ok(d["status"], running_host=True):
        bad("Status", f"Status `{d['status']}` is not proposed | approved | running@<host> | done | blocked: <reason>")
    if "Goal" in hl and not GOAL_RE.match(d["goal"]):
        bad("Goal", f"Goal `{d['goal']}` is not a goal name ({GOAL_RE.pattern})")
    if "Node" in hl and not re.match(r"^(any|tag:\S+|host:\S+)$", d["node"]):
        bad("Node", f"Node `{d['node']}` is not any | tag:<x> | host:<x>")
    deliverable_ok = d["deliverable"] in DELIVERABLES
    if "Deliverable" in hl and not deliverable_ok:
        bad("Deliverable", f"Deliverable `{d['deliverable']}` is not one of {' | '.join(DELIVERABLES)}")
    if "Land" in hl and d["land"] not in DIRECTIVE_LANDS:
        bad("Land", f"Land `{d['land']}` is not one of {' | '.join(DIRECTIVE_LANDS)}")
    if d["deliverable"] == "external":
        if "Verify" in hl and d["verify"] != "none":
            bad("Verify", "Verify must be `none` for Deliverable external")
        if d["land"] != "none":
            bad("Land" if "Land" in hl else "Deliverable", "Land must be `none` for Deliverable external")
    elif deliverable_ok and "Verify" in hl and not d["verify"]:
        bad("Verify", f"Verify must not be empty for Deliverable {d['deliverable']}")

    issues += _check_sections(md, DIRECTIVE_SECTIONS, path, acceptance=True)
    acc = _section(md, "Acceptance")
    if d["deliverable"] in ("doc", "slides", "external"):
        if acc is None:
            issues.append(Issue("error", path, 1, f"`## Acceptance` is required for Deliverable {d['deliverable']}"))
        elif not d["acceptance"]:
            issues.append(Issue("error", path, acc["line"], "`## Acceptance` needs at least one `- ` bullet"))

    steps_sec = _section(md, "Steps")
    if steps_sec:
        items, stray = _numbered(steps_sec["body"])
        issues += _check_numbering(items, stray, steps_sec, "step", path)
        for s in d["steps"]:
            if s["heavy"] and "Heavy because:" not in s["text"]:
                issues.append(Issue("error", path, s["line"],
                                    f"step {s['n']} is [heavy] but has no `Heavy because:`"))
    return issues


def validate_goal(gid: str, text: str) -> list[Issue]:
    """This one goal file's own rules (no cross-checks against directive files)."""
    path = str(GOAL_DIR / f"{gid}.md")
    md = _parse_md(text)
    g = parse_goal(text)
    hl = {k: ln for k, _, ln in reversed(md["headers"])}
    issues = _check_title(md, gid, "goal", GOAL_RE, path)
    if ID_RE.match(gid):
        issues.append(Issue("error", path, 1,
                            f"goal `{gid}` looks like a directive id ({ID_RE.pattern}); "
                            f"branch friday/{gid} would collide"))
    issues += _check_headers(md, GOAL_KEYS, (), path, warn_unknown=False)
    if "Status" in hl and not _status_ok(g["status"], running_host=False):
        issues.append(Issue("error", path, hl["Status"],
                            f"Status `{g['status']}` is not proposed | approved | running | done | blocked: <reason>"))
    if "Base" in hl and not g["base"]:
        issues.append(Issue("error", path, hl["Base"], "Base must not be empty"))
    if "Land" in hl and g["land"] not in GOAL_LANDS:
        issues.append(Issue("error", path, hl["Land"], f"Land `{g['land']}` is not one of {' | '.join(GOAL_LANDS)}"))

    issues += _check_sections(md, GOAL_SECTIONS, path, acceptance=False)
    sec = _section(md, "Directives")
    if sec:
        items, stray = _numbered(sec["body"])
        issues += _check_numbering(items, stray, sec, "directive", path)
        first: dict[str, int] = {}
        for it in g["directives"]:
            m = re.match(r"^([^\s:]+)(:\s|:$|$)", next(i["text"] for i in items if i["line"] == it["line"]))
            if not m or not ID_RE.match(it["id"]):
                issues.append(Issue("error", path, it["line"],
                                    f"item {it['n']} must start with a directive id, optionally `: <text>`"))
            elif it["id"] in first:
                issues.append(Issue("error", path, it["line"],
                                    f"directive `{it['id']}` listed twice (first on line {first[it['id']]})"))
            else:
                first[it["id"]] = it["line"]
    return issues


_SKIP = ("README.md", "TEMPLATE.md")


def _stems(folder: Path) -> list[str]:
    if not folder.is_dir():
        return []
    return sorted(f.stem for f in folder.glob("*.md") if f.name not in _SKIP)


def check_repo(root: Path | str, directive: str | None = None, goal: str | None = None) -> list[Issue]:
    """Issues for one directive, one goal (its file, its listed directives' files and the
    cross-checks), or (both None) every goal and directive file. README.md and TEMPLATE.md are
    skipped. Cross-checks: a directive's Goal file exists and lists it; every id a goal lists has
    a directive file; a listed directive names that goal. Warnings: a directive is done while an
    earlier one in its goal is not; a directive is approved while its goal is proposed."""
    root = Path(root)
    issues: list[Issue] = []
    seen: set = set()

    def add(items: list[Issue]) -> None:
        for i in items:
            if i not in seen:
                seen.add(i)
                issues.append(i)

    def read(p: Path) -> str | None:
        try:
            return p.read_text()
        except OSError:
            return None

    goals: dict[str, dict | None] = {}

    def load_goal(gid: str) -> dict | None:
        if gid not in goals:
            t = read(goal_path(root, gid))
            goals[gid] = parse_goal(t) if t is not None else None
        return goals[gid]

    def own_directive(did: str) -> dict | None:
        rel = str(DIRECTIVE_DIR / f"{did}.md")
        t = read(directive_path(root, did))
        if t is None:
            add([Issue("error", rel, 1, f"directive file {rel} does not exist")])
            return None
        add(validate_directive(did, t))
        return parse_directive_full(t)

    def own_goal(gid: str) -> dict | None:
        rel = str(GOAL_DIR / f"{gid}.md")
        t = read(goal_path(root, gid))
        if t is None:
            add([Issue("error", rel, 1, f"goal file {rel} does not exist")])
            return None
        add(validate_goal(gid, t))
        return load_goal(gid)

    def dstatus(did: str) -> str | None:
        t = read(directive_path(root, did))
        return parse_directive_full(t)["status"] if t is not None else None

    def cross_directive(did: str, d: dict) -> None:
        rel = str(DIRECTIVE_DIR / f"{did}.md")
        hl = {k: ln for k, _, ln in reversed(d["headers"])}
        gline = hl.get("Goal", 1)
        gid = d["goal"]
        if not gid or not GOAL_RE.match(gid):
            return
        g = load_goal(gid)
        grel = str(GOAL_DIR / f"{gid}.md")
        if g is None:
            add([Issue("error", rel, gline, f"Goal `{gid}`: {grel} does not exist")])
            return
        ids = [x["id"] for x in g["directives"]]
        if did not in ids:
            add([Issue("error", rel, gline, f"goal `{gid}` ({grel}) does not list {did}")])
            return
        if d["status"] == "done":
            for e in ids[:ids.index(did)]:
                if dstatus(e) != "done":
                    add([Issue("warning", rel, hl.get("Status", 1),
                               f"{did} is done but earlier directive {e} in goal `{gid}` is not")])
                    break
        if d["status"] == "approved" and g["status"] == "proposed":
            add([Issue("warning", rel, hl.get("Status", 1),
                       f"{did} is approved but goal `{gid}` is still proposed")])

    def cross_goal(gid: str, g: dict) -> None:
        grel = str(GOAL_DIR / f"{gid}.md")
        for x in g["directives"]:
            if not ID_RE.match(x["id"]):
                continue
            t = read(directive_path(root, x["id"]))
            if t is None:
                add([Issue("error", grel, x["line"],
                           f"directive `{x['id']}` is listed but {DIRECTIVE_DIR / (x['id'] + '.md')} does not exist")])
            elif parse_directive_full(t)["goal"] != gid:
                add([Issue("error", grel, x["line"],
                           f"directive `{x['id']}` is listed but its Goal is "
                           f"`{parse_directive_full(t)['goal']}`, not `{gid}`")])

    if directive is not None:
        d = own_directive(directive)
        if d:
            cross_directive(directive, d)
    elif goal is not None:
        g = own_goal(goal)
        if g:
            cross_goal(goal, g)
            for x in g["directives"]:
                if ID_RE.match(x["id"]) and read(directive_path(root, x["id"])) is not None:
                    d = own_directive(x["id"])
                    if d:
                        cross_directive(x["id"], d)
    else:
        for gid in _stems(root / GOAL_DIR):
            g = own_goal(gid)
            if g:
                cross_goal(gid, g)
        for did in _stems(root / DIRECTIVE_DIR):
            d = own_directive(did)
            if d:
                cross_directive(did, d)
    return issues


# ---------------------------------------------------------------- active marker
def marker_path(cwd: Path | str) -> Path | None:
    g = git_dir(cwd)
    return g / "friday-active" if g else None


def read_marker(cwd: Path | str) -> dict | None:
    p = marker_path(cwd)
    if not p:
        return None
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return None


def write_marker(cwd: Path | str, data: dict) -> None:
    p = marker_path(cwd)
    if p is None:
        raise RuntimeError("not inside a git repository")
    p.write_text(json.dumps(data))


def clear_marker(cwd: Path | str) -> None:
    p = marker_path(cwd)
    if p and p.exists():
        p.unlink()


# ---------------------------------------------------------------- shell parsing
_SEPARATORS = ("&&", "||", ";", "|", "\n", "&")


def split_commands(line: str) -> list[str]:
    """Split a shell line into simple commands on && || ; | & and newlines, outside quotes.
    Command substitutions $(...) and backticks are returned as extra commands too."""
    parts, buf, quote, i = [], [], None, 0
    subs = re.findall(r"\$\(([^()]*)\)|`([^`]*)`", line)
    while i < len(line):
        c = line[i]
        if quote:
            buf.append(c)
            if c == quote:
                quote = None
            elif c == "\\" and quote == '"' and i + 1 < len(line):
                buf.append(line[i + 1]); i += 1
            i += 1
            continue
        if c in "'\"":
            quote = c; buf.append(c); i += 1
            continue
        if c == "\\" and i + 1 < len(line):
            buf.append(c); buf.append(line[i + 1]); i += 2
            continue
        sep = next((s for s in _SEPARATORS if line.startswith(s, i)), None)
        if sep:
            parts.append("".join(buf)); buf = []; i += len(sep)
            continue
        buf.append(c); i += 1
    parts.append("".join(buf))
    for a, b in subs:
        parts.extend(split_commands(a or b))
    return [p.strip() for p in parts if p.strip()]


_PREFIXES = {"time", "nohup", "env", "exec", "command", "setsid", "nice", "stdbuf", "timeout"}


def argv_of(simple: str) -> list[str]:
    """argv of one simple command, minus leading VAR=value assignments and wrapper prefixes."""
    try:
        argv = shlex.split(simple, comments=False, posix=True)
    except ValueError:
        argv = simple.split()
    while argv:
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", argv[0]) or argv[0] in ("(", "{"):
            argv = argv[1:]
        elif argv[0] in _PREFIXES:
            argv = argv[1:]
            # the prefix's own flags and a duration/priority operand (timeout 60, nice -n 5)
            while argv and (argv[0].startswith("-") or re.match(r"^\d+[smhd]?$", argv[0])):
                argv = argv[1:]
        else:
            break
    return argv


# ---------------------------------------------------------------- leases
def lease_dir() -> Path:
    base = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    d = base / "friday" / "leases"
    d.mkdir(parents=True, exist_ok=True)
    return d


def lease_holder(resource: str, now: float | None = None) -> dict | None:
    p = lease_dir() / f"{resource}.json"
    try:
        lease = json.loads(p.read_text())
    except (OSError, ValueError):
        return None
    if (now or time.time()) - lease.get("time", 0) > LEASE_TTL_S:
        return None
    return lease


def take_lease(resource: str, session: str, note: str = "") -> None:
    p = lease_dir() / f"{resource}.json"
    p.write_text(json.dumps({"resource": resource, "session": session, "host": socket.gethostname(),
                             "time": time.time(), "note": note[:200]}))


def release_leases(session: str | None = None, resource: str | None = None) -> list[str]:
    released = []
    for p in lease_dir().glob("*.json"):
        try:
            lease = json.loads(p.read_text())
        except (OSError, ValueError):
            lease = {}
        if resource and p.stem != resource:
            continue
        if session and lease.get("session") != session:
            continue
        p.unlink(missing_ok=True)
        released.append(p.stem)
    return released


def list_leases() -> list[dict]:
    out = []
    for p in sorted(lease_dir().glob("*.json")):
        h = lease_holder(p.stem)
        if h:
            out.append(h)
    return out
