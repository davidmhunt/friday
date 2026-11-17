"""Shared logic for friday's hooks and the `friday` CLI. Standard library only.

Concepts
- Project config: `.claude/friday.json` at the repo root (optional; without it only the
  deny list applies). Keys: run_wrapper, run_only, hardware, verify.
- Directive: `docs/directives/<id>.md`, header lines `Status:`, `Node:`, `Verify:`, `Hardware:`.
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

LEASE_TTL_S = 4 * 3600
DIRECTIVE_DIR = Path("docs/directives")
HEADER_KEYS = ("Status", "Node", "Verify", "Hardware")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*-\d{2,}$")


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
