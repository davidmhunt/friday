"""`friday status --json`: one snapshot of this node. Standard library only; reads, never writes.

The snapshot (SCHEMA_VERSION 1) is the contract `friday dash` (status-02) stores and the
dashboard (status-03) shows. Its shape is declared once, in SCHEMA below, and check_schema()
holds any snapshot to it. Top-level keys:

- schema: 1; node: registry node name (the hostname when there is no registry); host: hostname;
  time: unix seconds when the snapshot was taken.
- health: uptime_s, load [1, 5, 15 min], mem {total, used} and disk {total, used} in bytes, disk
  for the filesystem that holds `repos`. Any value is null when it cannot be read.
- gpus[]: name, util (percent), mem {used, total} in MiB, processes [{pid, name, mem}].
  Empty without `nvidia-smi`.
- repos[]: path, origin, branch, goals[] {id, title, status, directives[] {id, status,
  deliverable, title}}. Directives not in any goal sit under a goal with id null.
- leases[]: resource, session, host, time, note (live hardware leases, as friday_core keeps them).
- runs[]: repo, id (directive), name (the `.exit` file stem), exit (int or null), mtime;
  the 10 newest per repo.
- sessions[]: one per `friday-*` tmux session: name, created, cwd, goal, directive, phase, step,
  waiting, waiting_line, snippet. See session_state() for how each is derived.
- errors[]: {where, error} for anything that could not be read or parsed; never a crash.
"""
from __future__ import annotations

import re
from pathlib import Path

import friday_core as fc

SCHEMA_VERSION = 1

# ---------------------------------------------------------------- schema
# A type spec: a Python type (or tuple of types; type(None) means nullable), a dict for an
# object with exactly these keys, or a one-element list for an array of that spec.
_N = type(None)
NUM = (int, float)
NUM_OR_NULL = (int, float, _N)
STR_OR_NULL = (str, _N)
_SIZE = {"total": NUM_OR_NULL, "used": NUM_OR_NULL}

SCHEMA = {
    "schema": int,
    "node": str,
    "host": str,
    "time": NUM,
    "health": {
        "uptime_s": NUM_OR_NULL,
        "load": ([NUM], _N),
        "mem": _SIZE,
        "disk": _SIZE,
    },
    "gpus": [{
        "name": str,
        "util": NUM_OR_NULL,
        "mem": _SIZE,
        "processes": [{"pid": int, "name": str, "mem": NUM_OR_NULL}],
    }],
    "repos": [{
        "path": str,
        "origin": STR_OR_NULL,
        "branch": STR_OR_NULL,
        "goals": [{
            "id": STR_OR_NULL,
            "title": str,
            "status": str,
            "directives": [{"id": str, "status": str, "deliverable": str, "title": str}],
        }],
    }],
    "leases": [{"resource": str, "session": str, "host": str, "time": NUM, "note": str}],
    "runs": [{"repo": str, "id": str, "name": str, "exit": (int, _N), "mtime": NUM}],
    "sessions": [{
        "name": str,
        "created": NUM_OR_NULL,
        "cwd": STR_OR_NULL,
        "goal": STR_OR_NULL,
        "directive": STR_OR_NULL,
        "phase": STR_OR_NULL,
        "step": STR_OR_NULL,
        "waiting": bool,
        "waiting_line": STR_OR_NULL,
        "snippet": [str],
    }],
    "errors": [{"where": str, "error": str}],
}


def _check(val, spec, path: str, out: list[str]) -> None:
    if isinstance(spec, tuple) and any(isinstance(s, (dict, list)) for s in spec):
        # a union with a structured member, e.g. ([NUM], None): first member that fits
        for s in spec:
            sub: list[str] = []
            _check(val, s, path, sub)
            if not sub:
                return
        out.append(f"{path}: {type(val).__name__} fits none of the allowed shapes")
    elif isinstance(spec, dict):
        if not isinstance(val, dict):
            out.append(f"{path}: expected object, got {type(val).__name__}")
            return
        for k in spec.keys() - val.keys():
            out.append(f"{path}.{k}: missing")
        for k in val.keys() - spec.keys():
            out.append(f"{path}.{k}: not in schema")
        for k in spec.keys() & val.keys():
            _check(val[k], spec[k], f"{path}.{k}", out)
    elif isinstance(spec, list):
        if not isinstance(val, list):
            out.append(f"{path}: expected array, got {type(val).__name__}")
            return
        for i, item in enumerate(val):
            _check(item, spec[0], f"{path}[{i}]", out)
    else:
        # bool is an int subclass; a bool is only valid where bool is asked for
        types = spec if isinstance(spec, tuple) else (spec,)
        if isinstance(val, bool) and bool not in types:
            out.append(f"{path}: expected {'/'.join(t.__name__ for t in types)}, got bool")
        elif not isinstance(val, types):
            out.append(f"{path}: expected {'/'.join(t.__name__ for t in types)}, got {type(val).__name__}")


def check_schema(snap) -> list[str]:
    """Every way `snap` departs from SCHEMA (empty list: it conforms), plus schema == 1."""
    out: list[str] = []
    _check(snap, SCHEMA, "$", out)
    if isinstance(snap, dict) and snap.get("schema") != SCHEMA_VERSION:
        out.append(f"$.schema: expected {SCHEMA_VERSION}, got {snap.get('schema')!r}")
    return out


def empty_snapshot(node: str, host: str, now: float) -> dict:
    """A snapshot with every key present and nothing collected; collectors fill it in."""
    return {
        "schema": SCHEMA_VERSION, "node": node, "host": host, "time": now,
        "health": {"uptime_s": None, "load": None,
                   "mem": {"total": None, "used": None}, "disk": {"total": None, "used": None}},
        "gpus": [], "repos": [], "leases": [], "runs": [], "sessions": [], "errors": [],
    }


# ---------------------------------------------------------------- session: waiting
# Every prompt that means "this session is stopped until a person answers", in one place.
# Matched case-insensitively against the last WAIT_WINDOW non-blank lines of the pane, newest
# first. Text Claude Code prints while it is busy or idle at its own input box ("❯ ") must not
# match. Add a pattern here, with a line in the tests, when a new prompt shows up.
WAIT_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("folder trust", re.compile(r"\bdo you trust the files in this folder\b"
                                r"|\byes, i trust this folder\b"
                                r"|\bis this a project you created or one you trust\b", re.I)),
    ("workflow", re.compile(r"\brun a dynamic workflow\?", re.I)),
    ("permission", re.compile(r"\bdo you want to (proceed|make this edit|create|allow|run|"
                              r"overwrite|delete|fetch|use)\b"
                              r"|\ballow (this|once|always)\b.*\?", re.I)),
    ("confirm", re.compile(r"\benter to confirm\b|\bpress enter to continue\b", re.I)),
]
WAIT_WINDOW = 10


def _tail(lines: list[str], n: int) -> list[str]:
    return [ln for ln in lines if ln.strip()][-n:]


def detect_waiting(lines: list[str]) -> tuple[bool, str | None]:
    """(True, the matching line) when the pane's last lines show a known prompt, else (False, None)."""
    for ln in reversed(_tail(lines, WAIT_WINDOW)):
        for _kind, rx in WAIT_PATTERNS:
            if rx.search(ln):
                return True, ln.strip()[:200]
    return False, None


# ---------------------------------------------------------------- session: phase and step
# The workflow status line Claude Code draws at the foot of the pane while a dynamic workflow
# runs, e.g. `◯ execute  ▰▰▰▰▰▱▱▱▱▱  2/3 · 47s · ↓ 39.4k tokens`, or bare `execute 3/4`.
# The whole line must be that shape, so prose such as "fleet-04 done (2/3 steps)" never matches.
WORKFLOW_LINE = re.compile(
    r"^\s*(?:[^\w\s]\s+)?"              # optional status glyph (◯ ● ✻ ...)
    r"(?P<name>[a-z][\w:.-]*)\s+"       # workflow name
    r"(?:[▰▱]+\s+)?"                    # optional progress bar
    r"(?P<done>\d+)/(?P<total>\d+)"     # progress
    r"\s*(?:·.*)?$")                    # optional `· 47s · ↓ 39.4k tokens`
STEP_WINDOW = 6


def detect_workflow(lines: list[str]) -> tuple[str | None, str | None]:
    """(workflow name, "done/total") from the newest workflow status line in the pane's foot."""
    for ln in reversed(_tail(lines, STEP_WINDOW)):
        m = WORKFLOW_LINE.match(ln)
        if m:
            return m.group("name"), f"{m.group('done')}/{m.group('total')}"
    return None, None


def session_state(name: str, created, cwd: str | None, pane: str,
                  marker: dict | None = None, snippet: list[str] | None = None) -> dict:
    """One `sessions[]` entry for tmux session `name`, from its pane text and its cwd.

    - directive: the `id` in the friday marker (`<git dir>/friday-active`) of `cwd`, else null.
    - goal: that directive's `Goal:` header; else the session name without `friday-`.
    - phase: the running workflow's name from its status line (e.g. `execute`); `started` when
      there is a marker but no workflow line; null when neither.
    - step: the status line's `done/total` (e.g. `3/4`), else null.
    - waiting / waiting_line: detect_waiting() over the pane.
    - snippet: given by the caller (redacted pane tail, step 2); [] here by default.
    `marker` may be passed in (tests); otherwise it is read from `cwd`.
    """
    lines = pane.splitlines()
    if marker is None and cwd:
        try:
            marker = fc.read_marker(cwd) if Path(cwd).is_dir() else None
        except OSError:
            marker = None
    directive = str(marker["id"]) if marker and marker.get("id") else None
    goal = None
    if directive and cwd:
        root = fc.repo_root(cwd)
        try:
            text = fc.directive_path(root, directive).read_text() if root else ""
            goal = fc.parse_directive_full(text).get("goal") or None if text else None
        except (OSError, ValueError):
            goal = None
    if not goal and name.startswith("friday-") and len(name) > len("friday-"):
        goal = name[len("friday-"):]
    wf, step = detect_workflow(lines)
    phase = wf or ("started" if directive else None)
    waiting, line = detect_waiting(lines)
    return {
        "name": name,
        "created": created,
        "cwd": cwd,
        "goal": goal,
        "directive": directive,
        "phase": phase,
        "step": step,
        "waiting": waiting,
        "waiting_line": line,
        "snippet": list(snippet or []),
    }
