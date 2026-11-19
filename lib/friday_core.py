"""Shared logic for friday's hooks and the `friday` CLI. Standard library only.

Concepts
- Project config: `.claude/friday.json` at the repo root (optional; without it only the
  deny list applies). Keys: run_wrapper, run_only, hardware.
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
# The read-only nodes listing and the dry-runs of dispatch and clean are allowed; the real
# `dispatch` and `nodes --clean` runs (and `release`) are deliberately left to prompt.
FRIDAY_ALLOW = [
    f"Bash(friday {c})"
    for c in ("status", "status *", "new *", "check *", "parse *", "start *",
              "verify", "verify *", "finish *", "commits *", "result *", "land *", "init", "session-end", "session-end *",
              "nodes", "nodes --check", "nodes --waiting", "nodes --clean * --dry-run", "dispatch --goal * --dry-run")
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


def _ref_exists(root: Path, ref: str) -> bool:
    return _git(["rev-parse", "--verify", "--quiet", ref + "^{commit}"], root) is not None


def directive_commits(root: Path | str, did: str) -> dict:
    """The directive's own change set: {"base", "commits": [(sha, subject)], "untracked":
    [(sha, subject, files)]}. Base is the merge-base of the goal's Base (local branch, else
    origin/<Base>) and the tip (HEAD; friday/<id> for `Land: pr` when that branch exists).
    `commits` are non-merge commits in base..tip with a `Directive: <id>` line, minus friday's own
    record commits and plan-only commits (files only under docs/goals/, docs/directives/, .claude/settings.json). `untracked` are non-merge commits with no `Directive:` line that touch
    anything outside docs/goals/ and docs/directives/. Raises ValueError when it cannot say."""
    root = Path(root)
    try:
        parsed = parse_directive_full(directive_path(root, did).read_text())
    except OSError as e:
        raise ValueError(f"cannot read directive {did}: {e}")
    gid = parsed["goal"]
    try:
        base_name = parse_goal(goal_path(root, gid).read_text())["base"]
    except OSError as e:
        raise ValueError(f"cannot read goal {gid!r} of {did}: {e}")
    if not base_name:
        raise ValueError(f"goal {gid} has no Base")
    for ref in (base_name, f"origin/{base_name}"):
        if _ref_exists(root, ref):
            base_ref = ref
            break
    else:
        raise ValueError(f"base branch '{base_name}' exists neither locally nor as origin/{base_name}")
    tip = "HEAD"
    if parsed["land"] == "pr" and _ref_exists(root, f"friday/{did}"):
        tip = f"friday/{did}"
    base = _git(["merge-base", base_ref, tip], root)
    if not base:
        raise ValueError(f"no merge-base of {base_ref} and {tip}")
    # Best-effort fetch so origin/<Base> is current; offline or no remote just keeps the local refs.
    _git(["fetch", "--quiet", "origin", base_name], root)
    base_refs = [r for r in (base_name, f"origin/{base_name}") if _ref_exists(root, r)]
    # Commits that reached the branch through a Base merge are not the directive's: anything on a
    # Base ref, and anything reachable from the second parent of a merge whose second parent is on Base.
    excl = list(base_refs)
    merges = _git(["rev-list", "--merges", "--parents", tip, "--not", *base_refs], root) or ""
    for line in merges.splitlines():
        parts = line.split()
        if len(parts) >= 3 and any(
                _git(["merge-base", "--is-ancestor", parts[2], r], root) is not None for r in base_refs):
            excl.append(parts[2])
    log = _git(["log", "--no-merges", "--reverse", "--format=%H%x00%B%x01", tip, "--not", *excl], root)
    if log is None:
        raise ValueError(f"git log {tip} failed")
    records = {f"{did}: {w}" for w in ("blocked", "unblock", "record results", "accepted")}
    trailer = re.compile(rf"(?m)^Directive:\s*{re.escape(did)}\s*$")
    anytrailer = re.compile(r"(?m)^Directive:\s*\S")
    commits: list[tuple[str, str]] = []
    untracked: list[tuple[str, str, list[str]]] = []
    for rec in log.split("\x01"):
        rec = rec.strip("\n")
        if not rec:
            continue
        sha, _, msg = rec.partition("\x00")
        subject = msg.strip().splitlines()[0] if msg.strip() else ""
        if subject in records:
            continue
        has = trailer.search(msg)
        if not has and anytrailer.search(msg):
            continue
        files = _git(["diff-tree", "--no-commit-id", "--name-only", "-r", "--root", sha], root)
        if files is None:
            raise ValueError(f"git diff-tree {sha} failed")
        fl = files.splitlines()
        # Plan commits live on the goal branch: they touch only goal/directive files (and the
        # settings `friday init` merges) and are never a directive's own work, trailer or not.
        if fl and all(f.startswith(("docs/goals/", "docs/directives/")) or f == ".claude/settings.json"
                      for f in fl):
            continue
        if has:
            commits.append((sha, subject))
        else:
            untracked.append((sha, subject, fl))
    return {"base": base, "commits": commits, "untracked": untracked}


# ---------------------------------------------------------------- config
def load_config(root: Path | None) -> dict:
    if root is None:
        return {}
    p = root / ".claude" / "friday.json"
    try:
        cfg = json.loads(p.read_text())
    except (OSError, ValueError):
        return {}
    if not isinstance(cfg, dict):
        return {}
    ha = cfg.get("hardware_approval")
    if "hardware_approval" in cfg:
        # invalid entries are rejected (dropped, so the resource stays `command`); `friday check` reports them
        hw = cfg.get("hardware") if isinstance(cfg.get("hardware"), dict) else {}
        cfg["hardware_approval"] = ({r: m for r, m in ha.items() if r in hw and m in APPROVAL_MODES}
                                    if isinstance(ha, dict) else {})
    if "rules" in cfg:
        # a non-list (or non-string entries) is dropped; `friday check` reports it
        r = cfg["rules"]
        cfg["rules"] = [x.strip() for x in r if isinstance(x, str) and x.strip()] if isinstance(r, list) else []
    return cfg


APPROVAL_MODES = ("command", "session")


def config_issues(root: Path | None) -> list[Issue]:
    """Errors for a bad `hardware_approval` in .claude/friday.json: a value other than `command`
    or `session`, or a resource that is not a key of `hardware`."""
    if root is None:
        return []
    rel = ".claude/friday.json"
    try:
        cfg = json.loads((root / rel).read_text())
    except (OSError, ValueError):
        return []
    if not isinstance(cfg, dict):
        return []
    out = []
    if "rules" in cfg:
        r = cfg["rules"]
        if not isinstance(r, list) or not all(isinstance(x, str) and x.strip() for x in r):
            out.append(Issue("error", rel, 1, "rules must be a list of non-empty strings"))
    if "hardware_approval" not in cfg:
        return out
    ha = cfg["hardware_approval"]
    if not isinstance(ha, dict):
        return out + [Issue("error", rel, 1, "hardware_approval must be an object: resource -> command|session")]
    known = cfg.get("hardware") if isinstance(cfg.get("hardware"), dict) else {}
    for res, mode in ha.items():
        if res not in known:
            out.append(Issue("error", rel, 1, f"hardware_approval names unknown resource `{res}` (not in hardware)"))
        if mode not in APPROVAL_MODES:
            out.append(Issue("error", rel, 1, f"hardware_approval `{res}` is {mode!r}; use command or session"))
    return out


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
DIRECTIVE_KEYS = ("Status", "Goal", "Node", "Deliverable", "Land", "Accept", "Verify", "Hardware")
ACCEPTS = ("auto", "user")
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


def _resolve_status_hunks(text: str) -> str | None:
    """Conflict-marked file text with every hunk replaced by its goal-branch ("ours") side, or None
    when any hunk has a line that is not a `Status:` line on either side."""
    out: list[str] = []
    part, ours, theirs = None, [], []
    for ln in text.splitlines(keepends=True):
        if part is None:
            if ln.startswith("<<<<<<< "):
                part, ours, theirs = "ours", [], []
            else:
                out.append(ln)
        elif ln.startswith("|||||||"):
            part = "base"
        elif ln.startswith("=======") and part in ("ours", "base"):
            part = "theirs"
        elif ln.startswith(">>>>>>> ") and part == "theirs":
            if any(not x.startswith("Status:") for x in ours + theirs):
                return None
            out.extend(ours)
            part = None
        elif part == "ours":
            ours.append(ln)
        elif part == "theirs":
            theirs.append(ln)
    return None if part is not None else "".join(out)


def resolve_status_conflicts(root: Path | str) -> list[str]:
    """After a conflicted `git merge` of Base into a goal branch: when every conflicted file is a
    docs/goals/*.md or docs/directives/*.md whose conflicting hunks are only `Status:` lines, keep the
    goal-branch side of those lines and stage the files. Returns [] on success, else the conflicted
    paths (nothing is changed then)."""
    root = Path(root)
    paths = (_git(["diff", "--name-only", "--diff-filter=U"], root) or "").split()
    fixed: dict[str, str] = {}
    for p in paths:
        pp = Path(p)
        if pp.parent not in (GOAL_DIR, DIRECTIVE_DIR) or pp.suffix != ".md":
            return paths
        f = root / p
        try:
            res = _resolve_status_hunks(f.read_text())
        except (OSError, UnicodeDecodeError):
            return paths
        if res is None:
            return paths
        fixed[p] = res
    for p, res in fixed.items():
        (root / p).write_text(res)
        if _git(["add", "--", p], root) is None:
            return paths
    return []


def reopen_done_goals(root: Path | str) -> list[str]:
    """Set a `done` goal back to `running` when it lists a directive that is not done (a goal amended
    after its PR opened). Edits the files in the working tree; returns the goal paths changed."""
    root = Path(root)
    changed = []
    gd = root / GOAL_DIR
    for gf in sorted(gd.glob("*.md")) if gd.is_dir() else []:
        try:
            text = gf.read_text()
            g = parse_goal(text)
        except (OSError, UnicodeDecodeError):
            continue
        if g["status"].strip().lower() != "done":
            continue
        undone = [x["id"] for x in g["directives"]
                  if ((read_directive(root, x["id"]) or {}).get("status", "").lower()
                      not in ("done", "awaiting review"))]
        if undone:
            gf.write_text(re.sub(r"(?m)^Status:.*$", "Status: running", text, count=1))
            changed.append(str(GOAL_DIR / gf.name))
    return changed



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


def _allowed_items(sec: dict | None) -> list[tuple[int, str, str | None]]:
    """`## Allowed commands` bullets as (line, bullet text, pattern or None when the bullet does
    not hold exactly one backticked span)."""
    out: list[tuple[int, str, str | None]] = []
    for i, line in (sec["body"] if sec else []):
        if line.startswith("- "):
            spans = re.findall(r"`([^`]*)`", line[2:])
            ok = len(spans) == 1 and line[2:].count("`") == 2 and spans[0].strip()
            out.append((i, line[2:].strip(), spans[0].strip() if ok else None))
    return out


def parse_directive_full(text: str) -> dict:
    """The parsed shape of a directive file. Keys: id, title, status, goal, node, deliverable,
    land (default `goal`), accept (default `auto`), verify, hardware, steps [{n, text, heavy, line}], acceptance [str]
    (None when there is no `## Acceptance`), review [str] (None when there is no `## Review`), rules [str] (`## Rules` bullets, [] when absent), allowed [str] (patterns in `## Allowed commands`, [] when absent), headers [(key, value, line)], sections [(name, line)]."""
    md = _parse_md(text)
    hm = _header_map(md)
    steps_sec = _section(md, "Steps")
    steps, _ = _numbered(steps_sec["body"]) if steps_sec else ([], [])
    for s in steps:
        # a `[heavy]` inside an inline code span is a mention of the marker, not the marker
        s["heavy"] = "[heavy]" in re.sub(r"`[^`]*`", "", s["text"])
    acc = _section(md, "Acceptance")
    rev = _section(md, "Review")
    return {
        "id": md["name"], "title": md["title"],
        **{k.lower(): hm.get(k, "") for k in DIRECTIVE_KEYS},
        "land": hm.get("Land", "goal") or "goal",
        "accept": hm.get("Accept", "auto") or "auto",
        "steps": [{"n": s["n"], "text": s["text"], "heavy": s["heavy"], "line": s["line"]}
                  for s in steps],
        "acceptance": _bullets(acc["body"]) if acc else None,
        "review": _bullets(rev["body"]) if rev else None,
        "rules": _bullets(rules["body"]) if (rules := _section(md, "Rules")) else [],
        "allowed": [p for _, _, p in _allowed_items(_section(md, "Allowed commands")) if p],
        "headers": md["headers"],
        "sections": [(s["name"], s["line"]) for s in md["sections"]],
    }


def parse_goal(text: str) -> dict:
    """The parsed shape of a goal file. Keys: goal, title, status, base, land, directives
    [{n, id, text, line}] (in list order), rules [str] (`## Rules` bullets), headers [(key, value, line)], sections [(name, line)]."""
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
        "rules": _bullets(rules["body"]) if (rules := _section(md, "Rules")) else [],
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
    once = required + (("Acceptance", "Review") if acceptance else ()) + ("Rules",)
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
    if running_host and status == "awaiting review":   # directives only
        return True
    if running_host:
        if re.match(r"^running@\S+$", status):
            return True
    elif status == "running":
        return True
    return bool(re.match(r"^blocked:\s*\S", status))


def _hook_deny(cmd: str) -> str | None:
    """The PreToolUse hook's deny list (hooks/friday_hook.py), loaded by path."""
    import importlib.util
    hp = Path(__file__).resolve().parent.parent / "hooks" / "friday_hook.py"
    spec = importlib.util.spec_from_file_location("friday_hook_deny", hp)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.check_deny(cmd)


def allowed_pattern_problem(pat: str) -> str | None:
    """Why an `## Allowed commands` pattern is not acceptable, or None."""
    if not pat.replace("*", "").strip():
        return "pattern matches everything; name a command"
    for bad in ("&&", ";", "|", "`", "$("):
        if bad in pat:
            return f"pattern contains `{bad}`; a pattern is one simple command"
    if re.match(r"^friday\s+accept\b", pat):
        return "`friday accept` can never be pre-approved"
    for probe in (pat, pat.replace("*", "x")):
        if (r := _hook_deny(probe)):
            return f"pattern matches the hook deny list ({r})"
    return None


_PUSH_PAT_VALUE_OPTS = {"--repo", "-o", "--push-option", "--receive-pack", "--exec", "--signed", "--recurse-submodules"}


def push_pattern_problem(pat: str, goal_branch: str) -> str | None:
    """Why a `git push` Allowed-commands pattern can never run (the push guard allows only the
    goal branch and explicit refs/tags/ pushes while a directive is active), or None."""
    try:
        toks = shlex.split(pat)
    except ValueError:
        return None
    if not toks or toks[0] != "git":
        return None
    i = 1
    while i < len(toks) and toks[i].startswith("-"):
        i += 2 if toks[i] in ("-C", "-c", "--git-dir", "--work-tree") else 1
    if i >= len(toks) or toks[i] != "push":
        return None
    why = ("the push guard denies this while the directive is active: only the goal branch "
           "and explicit refs/tags/ pushes")
    pos, args = [], toks[i + 1:]
    j = 0
    while j < len(args):
        a = args[j]
        if a in ("--all", "--mirror", "--branches", "--tags", "--follow-tags"):
            return f"`{a}`; {why}"
        if a in _PUSH_PAT_VALUE_OPTS:
            j += 2
            continue
        if not a.startswith("-"):
            pos.append(a)
        j += 1
    specs = pos[1:]
    if not specs:
        return None
    if len(specs) >= 2 and specs[0] == "tag":
        return None if len(specs) % 2 == 0 and all(specs[k] == "tag" for k in range(0, len(specs), 2)) \
            else f"unrecognised tag push; {why}"
    is_tag = [sp.lstrip("+").rsplit(":", 1)[-1].startswith("refs/tags/")
              and len(sp.lstrip("+").rsplit(":", 1)[-1]) > len("refs/tags/") for sp in specs]
    if any(is_tag) and not all(is_tag):
        return f"a push mixing tag and branch destinations is always denied; {why}"
    for sp in specs:
        dst = sp.lstrip("+").rsplit(":", 1)[-1]
        if dst.startswith("refs/heads/"):
            dst = dst[len("refs/heads/"):]
        if dst == "*":
            return f"the destination is a bare `*`; {why}"
        if dst.startswith("refs/tags/") and len(dst) > len("refs/tags/"):
            continue
        if dst != goal_branch:
            return f"destination `{dst}` is not the goal branch {goal_branch} or an explicit refs/tags/ ref; {why}"
    return None


_SSH_VALUE_OPTS = {"-p", "-i", "-o", "-J", "-l", "-F"}
_REMOTE_SHELLS = {"bash", "sh", "zsh", "dash"}
_REMOTE_BUILDS = (("docker", "build"), ("colcon", "build"), ("make",), ("cmake",), ("cargo", "build"),
                  ("pip", "install"), ("pip3", "install"), ("uv", "sync"), ("apt",), ("apt-get",))
_THIN_RULE = ("a target directive runs named, reviewed scripts and single-purpose writes; "
              "iterative robot work is a worker goal (`Node: host:<robot>`, see docs/fleet.md "
              "\"Targets and workers\")")


def remote_pattern_warnings(pat: str) -> list[str]:
    """Warnings for an `## Allowed commands` pattern that is an `ssh` call pre-approving any
    remote command, a remote shell, or a remote build/install. [] for anything else."""
    argv = argv_of(pat)
    if not argv or argv[0] != "ssh":
        return []
    i = 1
    while i < len(argv) and argv[i].startswith("-"):
        i += 2 if argv[i] in _SSH_VALUE_OPTS else 1
    if i >= len(argv):
        return []
    rest = argv[i + 1:]                      # argv[i] is the host
    if len(rest) == 1 and " " in rest[0]:    # ssh host 'docker build .'
        rest = argv_of(rest[0])
    if not rest or rest[0].startswith("*"):
        return [f"`{pat}` pre-approves any remote command; {_THIN_RULE}"]
    if rest[0] in _REMOTE_SHELLS and ("-c" in rest[1:] or any("*" in t for t in rest[1:])):
        return [f"`{pat}` pre-approves an arbitrary remote shell command; {_THIN_RULE}"]
    for b in _REMOTE_BUILDS:
        if tuple(rest[:len(b)]) == b:
            return [f"`{pat}` is a remote build or install; {_THIN_RULE}"]
    return []


def validate_directive(did: str, text: str) -> list[Issue]:
    """This one directive file's own rules (no cross-checks against goal files)."""
    path = str(DIRECTIVE_DIR / f"{did}.md")
    md = _parse_md(text)
    d = parse_directive_full(text)
    hl = {k: ln for k, _, ln in reversed(md["headers"])}   # first line of each key
    issues = _check_title(md, did, "id", ID_RE, path)
    issues += _check_headers(md, DIRECTIVE_KEYS, ("Land", "Accept"), path, warn_unknown=True)

    def bad(key: str, msg: str) -> None:
        issues.append(Issue("error", path, hl.get(key, 1), msg))

    if "Status" in hl and not _status_ok(d["status"], running_host=True):
        bad("Status", f"Status `{d['status']}` is not proposed | approved | running@<host> | awaiting review | done | blocked: <reason>")
    if "Goal" in hl and not GOAL_RE.match(d["goal"]):
        bad("Goal", f"Goal `{d['goal']}` is not a goal name ({GOAL_RE.pattern})")
    if "Node" in hl and not re.match(r"^(any|tag:\S+|host:\S+)$", d["node"]):
        bad("Node", f"Node `{d['node']}` is not any | tag:<x> | host:<x>")
    deliverable_ok = d["deliverable"] in DELIVERABLES
    if "Deliverable" in hl and not deliverable_ok:
        bad("Deliverable", f"Deliverable `{d['deliverable']}` is not one of {' | '.join(DELIVERABLES)}")
    if "Hardware" in hl and not d["hardware"].strip():
        bad("Hardware", "Hardware must not be empty (use `none` or a resource name)")
    if "Accept" in hl and d["accept"] not in ACCEPTS:
        bad("Accept", f"Accept `{d['accept']}` is not one of {' | '.join(ACCEPTS)}")
    if "Land" in hl and d["land"] not in DIRECTIVE_LANDS:
        bad("Land", f"Land `{d['land']}` is not one of {' | '.join(DIRECTIVE_LANDS)}")
    if d["deliverable"] == "external":
        if "Verify" in hl and d["verify"] != "none":
            bad("Verify", "Verify must be `none` for Deliverable external")
        if d["land"] != "none":
            bad("Land" if "Land" in hl else "Deliverable", "Land must be `none` for Deliverable external")
    elif deliverable_ok and "Verify" in hl and not d["verify"]:
        bad("Verify", f"Verify must not be empty for Deliverable {d['deliverable']}")
    elif deliverable_ok and "Verify" in hl and d["verify"].strip().lower() == "none":
        bad("Verify", f"Verify `none` is only for Deliverable external, not {d['deliverable']}")

    issues += _check_sections(md, DIRECTIVE_SECTIONS, path, acceptance=True)
    acc = _section(md, "Acceptance")
    if d["deliverable"] in ("doc", "slides", "external"):
        if acc is None:
            issues.append(Issue("error", path, 1, f"`## Acceptance` is required for Deliverable {d['deliverable']}"))
        elif not d["acceptance"]:
            issues.append(Issue("error", path, acc["line"], "`## Acceptance` needs at least one `- ` bullet"))

    rules_sec = _section(md, "Rules")
    if rules_sec is not None and not _bullets(rules_sec["body"]):
        issues.append(Issue("error", path, rules_sec["line"], "`## Rules` needs at least one `- ` bullet"))

    rev = _section(md, "Review")
    if d["accept"] == "user":
        if rev is None:
            issues.append(Issue("error", path, hl.get("Accept", 1), "`## Review` is required with `Accept: user`"))
        elif not d["review"]:
            issues.append(Issue("error", path, rev["line"], "`## Review` needs at least one `- ` bullet"))
    elif d["deliverable"] == "external":
        issues.append(Issue("warning", path, hl.get("Deliverable", 1),
                            "Deliverable external should use `Accept: user` (with a `## Review` section)"))

    for ln, text, pat in _allowed_items(_section(md, "Allowed commands")):
        if pat is None:
            issues.append(Issue("error", path, ln, f"Allowed commands bullet needs exactly one backticked pattern: {text}"))
        elif (why := allowed_pattern_problem(pat)):
            issues.append(Issue("error", path, ln, f"Allowed commands `{pat}`: {why}"))
        elif (why := push_pattern_problem(
                pat, f"friday/{did}" if d["land"] == "pr" else f"friday/{d['goal']}")):
            issues.append(Issue("error", path, ln, f"Allowed commands `{pat}`: {why}"))
        else:
            for w in remote_pattern_warnings(pat):
                issues.append(Issue("warning", path, ln, f"Allowed commands {w}"))

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
    rules_sec = _section(md, "Rules")
    if rules_sec is not None and not _bullets(rules_sec["body"]):
        issues.append(Issue("error", path, rules_sec["line"], "`## Rules` needs at least one `- ` bullet"))
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


def hardware_verify_warnings(root: Path, rel: str, d: dict) -> list[Issue]:
    """Warn when Verify matches a `hardware` pattern in .claude/friday.json: Verify is re-run
    unattended (fix rounds, landing) without the hardware prompt."""
    verify = d.get("verify") or ""
    if not verify:
        return []
    ln = next((n for k, _, n in reversed(d["headers"]) if k == "Verify"), 1)
    out = []
    for resource, patterns in (load_config(root).get("hardware") or {}).items():
        for pat in patterns:
            try:
                hit = re.search(pat, verify)
            except re.error:
                continue
            if hit:
                out.append(Issue("warning", rel, ln,
                                 f"Verify matches hardware pattern `{pat}` ({resource}) but is re-run unattended "
                                 "without the hardware prompt; run the device step once, record it with "
                                 "`friday result write`, and make Verify a `friday result check`"))
                break
    return out


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

    add(config_issues(root))
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
        d = parse_directive_full(t)
        add(hardware_verify_warnings(root, rel, d))
        return d

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


_SUBST = r"\$\(([^()]*)\)|`([^`]*)`"


def split_commands(line: str) -> list[str]:
    """Split a shell line into simple commands on && || ; | & and newlines, outside quotes.
    Command substitutions $(...) and backticks are returned as extra commands too.
    Heredoc bodies are scanned like any other text (fail closed)."""
    parts, buf, quote, i = [], [], None, 0
    subs = re.findall(_SUBST, line)
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


def waiting_dir() -> Path:
    """`~/.local/state/friday/waiting/`: one `<goal>.json` per session stopped on a prompt."""
    base = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    return base / "friday" / "waiting"


def lease_holder(resource: str, now: float | None = None) -> dict | None:
    p = lease_dir() / f"{resource}.json"
    try:
        lease = json.loads(p.read_text())
    except (OSError, ValueError):
        return None
    if (now or time.time()) - lease.get("time", 0) > LEASE_TTL_S:
        return None
    return lease


def take_lease(resource: str, session: str, note: str = "", approved: bool = False) -> None:
    p = lease_dir() / f"{resource}.json"
    lease = {"resource": resource, "session": session, "host": socket.gethostname(),
             "time": time.time(), "note": note[:200]}
    if approved:
        lease["approved"] = True
    p.write_text(json.dumps(lease))


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


# ---------------------------------------------------------------- git commit-msg guard
HOOK_TAG = "# friday-commit-msg-hook"
COMMIT_MSG_HOOK = '''#!/usr/bin/env python3
''' + HOOK_TAG + '''
# Installed by `friday init` / `friday start`; removed by `friday uninstall`.
# While a directive is active in this worktree, refuse commits without `Directive: <id>`.
import json, os, re, subprocess, sys

def git(*a):
    r = subprocess.run(["git", *a], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""

msgfile = sys.argv[1] if len(sys.argv) > 1 else ""
local = os.path.join(os.path.dirname(os.path.abspath(__file__)), "commit-msg.local")
if os.path.isfile(local) and os.access(local, os.X_OK):
    rc = subprocess.run([local, *sys.argv[1:]]).returncode
    if rc:
        sys.exit(rc)

gd = git("rev-parse", "--absolute-git-dir")
try:
    marker = json.load(open(os.path.join(gd, "friday-active")))
    did = marker["id"]
except (OSError, ValueError, KeyError, TypeError):
    sys.exit(0)
try:
    msg = open(msgfile, errors="replace").read()
except OSError:
    sys.exit(0)
msg = "\\n".join(l for l in msg.splitlines() if not l.startswith("#"))
named = re.findall(r"(?m)^Directive:[ \\t]*(\\S+)[ \\t]*$", msg)
if did in named:
    sys.exit(0)

def goal_of(x):
    top = git("rev-parse", "--show-toplevel")
    try:
        t = open(os.path.join(top, "docs", "directives", x + ".md")).read()
    except OSError:
        return None
    m = re.search(r"(?m)^Goal:[ \\t]*(\\S+)", t)
    return m.group(1) if m else None

staged = git("diff", "--cached", "--name-only").splitlines()
if staged and all(f.startswith(("docs/goals/", "docs/directives/")) for f in staged):
    g = goal_of(did)
    if g and any(goal_of(n) == g for n in named):
        sys.exit(0)

sys.stderr.write(
    f"friday: directive {did} is active in this worktree, so every commit needs the line\\n"
    f"    Directive: {did}\\n"
    f"as the last line of its message (git commit -m 'what changed' -m 'Directive: {did}').\\n"
    f"To commit without it on purpose: git commit --no-verify\\n")
sys.exit(1)
'''


def hooks_dir(root: Path | str) -> Path:
    p = _git(["rev-parse", "--git-path", "hooks"], Path(root))
    d = Path(p)
    return d if d.is_absolute() else Path(root) / d


def install_commit_hook(root: Path | str) -> str:
    """Install friday's commit-msg; an existing foreign one becomes commit-msg.local. Idempotent.
    Returns "installed", "unchanged" or "blocked" (a foreign hook and a commit-msg.local both exist)."""
    d = hooks_dir(root)
    hook, local = d / "commit-msg", d / "commit-msg.local"
    if hook.is_file() and not hook.is_symlink():
        text = hook.read_text(errors="replace")
        if HOOK_TAG in text:
            if text == COMMIT_MSG_HOOK and os.access(hook, os.X_OK):
                return "unchanged"
        elif local.exists():
            return "blocked"
        else:
            hook.rename(local)
    elif hook.exists() or hook.is_symlink():
        if local.exists():
            return "blocked"
        hook.rename(local)
    d.mkdir(parents=True, exist_ok=True)
    hook.write_text(COMMIT_MSG_HOOK)
    hook.chmod(0o755)
    return "installed"


def uninstall_commit_hook(root: Path | str) -> bool:
    d = hooks_dir(root)
    hook, local = d / "commit-msg", d / "commit-msg.local"
    if not (hook.is_file() and HOOK_TAG in hook.read_text(errors="replace")):
        return False
    hook.unlink()
    if local.exists():
        local.rename(hook)
    return True


def merged_rules(root: Path | None, *own: list[str]) -> list[str]:
    """Repo rules (.claude/friday.json `rules`), then each of `own` (goal's, directive's), in order, deduplicated."""
    out: list[str] = []
    for r in [(load_config(root).get("rules") or []), *own]:
        for x in r:
            if x not in out:
                out.append(x)
    return out
