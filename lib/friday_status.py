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
- repos[]: path, origin, branch, goals[] {id, title, status, pr (none|open|merged; closed on GitLab) and pr_url (both
  left out without gh), plan (published | not published | stale; only on a running goal whose
  directives have Allowed commands), directives[] {id, status,
  deliverable, title}}. Directives not in any goal sit under a goal with id null.
- leases[]: resource, session, host, time, note (live hardware leases, as friday_core keeps them).
- runs[]: repo, id (directive), name (the `.exit` file stem), exit (int or null), mtime;
  the 10 newest per repo.
- sessions[]: one per `friday-*` tmux session: name, created, cwd, goal, directive, phase, step,
  waiting, waiting_line, snippet. See session_state() for how each is derived.
- errors[]: {where, error} for anything that could not be read or parsed; never a crash.
"""
from __future__ import annotations

import json
import re
import shutil
import os
import socket
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace

import friday_core as fc
import friday_fleet as ff

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
    "push_mode": str,
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
        "forge": str,
        "branch": STR_OR_NULL,
        "goals": [{
            "id": STR_OR_NULL,
            "title": str,
            "status": str,
            "pr": str,
            "pr_url": STR_OR_NULL,
            "plan": STR_OR_NULL,
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
        "waiting_age": NUM_OR_NULL,
        "snippet": [str],
    }],
    "errors": [{"where": str, "error": str}],
}


# Keys a snapshot may leave out: a goal's pr / pr_url are absent when gh is unavailable.
OPTIONAL_KEYS = {"pr", "pr_url", "push_mode", "plan", "forge"}


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
        for k in spec.keys() - val.keys() - OPTIONAL_KEYS:
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
        "push_mode": os.environ.get("FRIDAY_PUSH_MODE") or "timer",
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


# ---------------------------------------------------------------- session: snippet
# Secrets that must never leave the node. One list; each pattern's match (or, with a `value`
# group, just that group) becomes REDACTED. Add a pattern here with a line in the tests.
REDACTED = "[redacted]"
REDACT_PATTERNS: list[tuple[str, re.Pattern]] = [
    # a PEM block; an unterminated one (END scrolled off or not yet drawn) runs to the end
    ("private key", re.compile(r"-----BEGIN [A-Z0-9 ]*KEY-----.*?(?:-----END [A-Z0-9 ]*KEY-----|\Z)", re.S)),
    ("openai/anthropic key", re.compile(r"\bsk-[A-Za-z0-9_-]{8,}")),
    ("github token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{8,}|\bgithub_pat_[A-Za-z0-9_]{8,}")),
    ("aws access key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{12,}\b")),
    ("authorization", re.compile(r"(?i)\bauthorization\s*[:=]\s*(?:(?:bearer|basic|token)\s+)?(?P<value>[^\s'\"]+)")),
    ("assignment", re.compile(r"(?i)\b(?:password|passwd|token|secret|api[_-]?key)\s*[=:]\s*(?P<value>[^\s'\"&;]+)")),
]
SNIPPET_LINES = 12
SNIPPET_WIDTH = 200


def redact(text: str) -> str:
    """`text` with every REDACT_PATTERNS match replaced by [redacted]."""
    for _name, rx in REDACT_PATTERNS:
        if "value" in rx.groupindex:
            text = rx.sub(lambda m: m.group(0)[:m.start("value") - m.start()] + REDACTED, text)
        else:
            text = rx.sub(REDACTED, text)
    return text


def make_snippet(pane: str) -> list[str]:
    """The last SNIPPET_LINES non-blank pane lines, redacted, each cut to SNIPPET_WIDTH.

    Redaction runs on the whole pane first (a key block spans lines) and the cut comes after,
    so a secret is never left half-visible at a cut.
    """
    lines = _tail(redact(pane).splitlines(), SNIPPET_LINES)
    return [ln.rstrip()[:SNIPPET_WIDTH] for ln in lines]


def fmt_age(secs) -> str:
    s = max(0, int(secs))
    return f"{s}s" if s < 90 else f"{round(s / 60)}m" if s < 5400 else f"{round(s / 3600)}h"


def read_waiting_record(goal: str) -> dict | None:
    """The hook's `<goal>.json` record of a session stopped on a prompt, or None."""
    try:
        rec = json.loads((fc.waiting_dir() / f"{goal}.json").read_text())
    except (OSError, ValueError):
        return None
    return rec if isinstance(rec, dict) else None


def session_state(name: str, created, cwd: str | None, pane: str,
                  marker: dict | None = None, snippet: list[str] | None = None,
                  record: dict | None = None, now: float | None = None) -> dict:
    """One `sessions[]` entry for tmux session `name`, from its pane text and its cwd.

    - directive: the `id` in the friday marker (`<git dir>/friday-active`) of `cwd`, else null.
    - goal: that directive's `Goal:` header; else the session name without `friday-`.
    - phase: the running workflow's name from its status line (e.g. `execute`); `started` when
      there is a marker but no workflow line; null when neither.
    - step: the status line's `done/total` (e.g. `3/4`), else null.
    - waiting / waiting_line / waiting_age: the hook's record `<state>/friday/waiting/<goal>.json`
      (message, seconds since it was written) when there is one, else detect_waiting() over the
      pane (waiting_age null). `record` may be passed in (tests).
    - snippet: make_snippet(pane), redacted; `snippet` may be passed in (tests).
    `marker` may be passed in (tests); otherwise it is read from `cwd`.
    """
    pane = redact(pane)  # nothing derived from the pane below can carry a secret
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
    if record is None and goal:
        record = read_waiting_record(goal)
    if record and record.get("message") is not None:
        waiting, line = True, redact(str(record["message"]))[:SNIPPET_WIDTH] or "waiting for input"
        t = record.get("time")
        age = (max(0.0, (time.time() if now is None else now) - t)
               if isinstance(t, (int, float)) and not isinstance(t, bool) else None)
    else:
        waiting, line = detect_waiting(lines)
        age = None
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
        "waiting_age": age,
        "snippet": list(snippet) if snippet is not None else make_snippet(pane),
    }


# ---------------------------------------------------------------- collectors
# Every external command is optional with a 3 s timeout: missing or slow means empty or null.
CMD_TIMEOUT = 3
RUNS_PER_REPO = 10
PANE_LINES = 60


def _run(argv: list[str], cwd=None) -> str | None:
    """stdout of `argv`, or None when it is missing, slow, or fails."""
    try:
        r = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=CMD_TIMEOUT)
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None
    return r.stdout if r.returncode == 0 else None


def _num(s: str):
    """A number from an nvidia-smi / proc field, or None (`[N/A]`, empty, junk)."""
    try:
        f = float(s.strip())
    except ValueError:
        return None
    return int(f) if f == int(f) else f


def collect_health(proc_root: str | Path, disk_path, errors: list) -> dict:
    """health from <proc_root>/uptime, loadavg, meminfo and shutil.disk_usage(disk_path)."""
    proc = Path(proc_root)
    h = {"uptime_s": None, "load": None, "mem": {"total": None, "used": None},
         "disk": {"total": None, "used": None}}
    try:
        h["uptime_s"] = float((proc / "uptime").read_text().split()[0])
    except (OSError, ValueError, IndexError) as e:
        errors.append({"where": "health.uptime", "error": str(e)})
    try:
        h["load"] = [float(x) for x in (proc / "loadavg").read_text().split()[:3]]
        if len(h["load"]) != 3:
            raise ValueError("loadavg has fewer than 3 values")
    except (OSError, ValueError) as e:
        h["load"] = None
        errors.append({"where": "health.load", "error": str(e)})
    try:
        kb = {}
        for ln in (proc / "meminfo").read_text().splitlines():
            m = re.match(r"^(\w+):\s+(\d+)", ln)
            if m:
                kb[m.group(1)] = int(m.group(2)) * 1024
        total = kb["MemTotal"]
        avail = kb.get("MemAvailable", kb.get("MemFree", 0) + kb.get("Buffers", 0) + kb.get("Cached", 0))
        h["mem"] = {"total": total, "used": max(total - avail, 0)}
    except (OSError, KeyError) as e:
        errors.append({"where": "health.mem", "error": f"unreadable: {e!r}"})
    try:
        du = shutil.disk_usage(disk_path)
        h["disk"] = {"total": du.total, "used": du.used}
    except OSError as e:
        errors.append({"where": "health.disk", "error": str(e)})
    return h


def collect_gpus(errors: list) -> list[dict]:
    """gpus[] from nvidia-smi; [] when it is absent or fails."""
    out = _run(["nvidia-smi", "--query-gpu=index,uuid,name,utilization.gpu,memory.used,memory.total",
                "--format=csv,noheader,nounits"])
    if out is None:
        return []
    gpus, by_uuid = [], {}
    for ln in out.splitlines():
        if not ln.strip():
            continue
        f = [x.strip() for x in ln.split(",")]
        if len(f) < 6:
            errors.append({"where": "gpus", "error": f"unparsable line: {ln[:100]}"})
            continue
        name = ",".join(f[2:-3])
        g = {"name": name, "util": _num(f[-3]), "mem": {"used": _num(f[-2]), "total": _num(f[-1])},
             "processes": []}
        gpus.append(g)
        by_uuid[f[1]] = g
    apps = _run(["nvidia-smi", "--query-compute-apps=gpu_uuid,pid,process_name,used_memory",
                 "--format=csv,noheader,nounits"])
    for ln in (apps or "").splitlines():
        f = [x.strip() for x in ln.split(",")]
        if len(f) < 4 or not f[1].isdigit():
            if ln.strip():
                errors.append({"where": "gpus.processes", "error": f"unparsable line: {ln[:100]}"})
            continue
        g = by_uuid.get(f[0])
        if g is not None:
            g["processes"].append({"pid": int(f[1]), "name": ",".join(f[2:-1]), "mem": _num(f[-1])})
    return gpus


def _is_friday_repo(p: Path) -> bool:
    return (p / ".git").exists() and ((p / "docs" / "goals").is_dir() or (p / "docs" / "directives").is_dir())


def registry_node(registry_path=None, node_name: str | None = None, errors: list | None = None):
    """This node's registry entry (matched on name or ssh against node_name/hostname); else
    the node identity file as a (name, repos) entry; else None."""
    errors = errors if errors is not None else []
    try:
        reg_file = Path(registry_path) if registry_path else ff.find_nodes_file()
        if reg_file:
            reg = ff.load_nodes(reg_file)
            names = {node_name, socket.gethostname()} if node_name else {socket.gethostname()}
            hit = next((n for n in reg.nodes.values() if n.name in names or n.ssh in names), None)
            if hit:
                return hit
    except ff.RegistryError as e:
        errors.append({"where": "registry", "error": str(e)})
    try:
        nf = ff.load_node_file()
    except ff.RegistryError as e:
        errors.append({"where": "node file", "error": str(e)})
        return None
    if nf:
        return SimpleNamespace(name=nf[0], repos=nf[1], ssh="")
    return None


def find_repos(cwd, registry_path=None, node_name: str | None = None, errors: list | None = None,
               node=None) -> list[Path]:
    """This node's friday repos: the checkouts under its registry `repos` (and their
    `<repo>.friday/<goal>` worktrees), else the repo containing `cwd` (and its worktrees)."""
    errors = errors if errors is not None else []
    bases: list[Path] = []
    if node is None:
        node = registry_node(registry_path, node_name, errors)
    if node and node.repos:
        bases.append(Path(node.repos).expanduser())
    found: list[Path] = []
    if bases:
        for base in bases:
            try:
                kids = sorted(base.iterdir())
            except OSError as e:
                errors.append({"where": f"repos {base}", "error": str(e)})
                continue
            found += [k for k in kids if k.is_dir() and not k.name.endswith(".friday") and _is_friday_repo(k)]
    else:
        root = fc.repo_root(cwd)
        if root is not None:
            # a goal worktree is `<repo>.friday/<goal>`; its main checkout is the repo
            main = root.parent.parent / root.parent.name[:-len(".friday")] if root.parent.name.endswith(".friday") else root
            found.append(main if _is_friday_repo(main) else root)
    out: list[Path] = []
    for r in found:
        out.append(r)
        wt = r.parent / f"{r.name}.friday"
        try:
            out += [w for w in sorted(wt.iterdir()) if w.is_dir() and _is_friday_repo(w)] if wt.is_dir() else []
        except OSError as e:
            errors.append({"where": f"worktrees {wt}", "error": str(e)})
    seen, uniq = set(), []
    for p in out:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    return uniq


def goal_pr(path: Path, goal: str, gh: str | None, glab: str | None = None) -> tuple[str, str | None] | None:
    """(state, url) of the PR (GitLab: MR) from `friday/<goal>`: state is none, open or merged, plus closed on GitLab (a closed
    unmerged MR; on GitHub a closed unmerged PR still counts as none, as scope-01 settled). A `forge: none` repo (set in .claude/friday.json) is always none. None when the forge's CLI (gh, or glab
    for a GitLab repo) is missing or fails: the caller leaves the keys out."""
    f = fc.forge(path)
    kind = f["kind"]
    if kind == "none" and fc.load_config(path).get("forge") == "none":
        return "none", None  # configured as having no forge: nothing to ask (otherwise gh is tried, as before)
    if kind == "gitlab":
        glab = glab or os.environ.get("FRIDAY_GLAB") or shutil.which("glab")
        if not glab:
            return None
        out = _run([glab, "mr", "list", "--source-branch", f"friday/{goal}", "--all", "--output", "json"],
                   cwd=path)
        key, num = "iid", {"opened": "open", "open": "open", "merged": "merged", "closed": "closed"}
    else:
        if not gh:
            return None
        out = _run([gh, "pr", "list", "--head", f"friday/{goal}", "--state", "all",
                    "--json", "state,url,number"], cwd=path)
        key, num = "number", {"open": "open", "merged": "merged"}
    if out is None:
        return None
    try:
        prs = json.loads(out)
    except ValueError:
        return None
    if not isinstance(prs, list):
        return None
    prs = [p for p in prs if isinstance(p, dict)]
    for want in ("open", "merged") + (("closed",) if kind == "gitlab" else ()):
        for pr in sorted(prs, key=lambda x: -(x.get(key) or x.get("number") or 0)):
            if num.get(str(pr.get("state", "")).lower()) == want:
                return want, pr.get("web_url") or pr.get("url")
    return "none", None


def goal_plan_state(path: Path, dids: list[str]) -> str | None:
    """Worst publish state (stale, not published, published) over the directives with Allowed
    commands, or None when none has any."""
    states = [s for s in (fc.plan_publish_state(path, d) for d in dids) if s]
    for bad in ("stale", "not published"):
        if bad in states:
            return bad
    return "published" if states else None


def collect_repo(path: Path, errors: list) -> dict:
    """One repos[] entry: origin, branch, and every goal with its directives' statuses."""
    origin = _run(["git", "config", "--get", "remote.origin.url"], cwd=path)
    branch = _run(["git", "symbolic-ref", "--quiet", "--short", "HEAD"], cwd=path)
    directives: dict[str, dict] = {}
    ddir = path / fc.DIRECTIVE_DIR
    for p in sorted(ddir.glob("*.md")) if ddir.is_dir() else []:
        if p.name.upper() == "README.MD" or p.stem.upper() == "TEMPLATE":
            continue
        try:
            d = fc.parse_directive_full(p.read_text())
            directives[p.stem] = {"id": p.stem, "status": d.get("status") or "", "title": d.get("title") or "",
                                  "deliverable": d.get("deliverable") or ""}
        except Exception as e:  # a broken file is an entry in errors[], not a crash
            errors.append({"where": str(p), "error": f"{type(e).__name__}: {e}"})
    goals, listed = [], set()
    gh = os.environ.get("FRIDAY_GH") or shutil.which("gh")
    gdir = path / fc.GOAL_DIR
    for p in sorted(gdir.glob("*.md")) if gdir.is_dir() else []:
        if p.name.upper() in ("README.MD", "TEMPLATE.MD"):
            continue
        try:
            g = fc.parse_goal(p.read_text())
            items = []
            for x in g["directives"]:
                listed.add(x["id"])
                items.append(directives.get(x["id"]) or
                             {"id": x["id"], "status": "missing", "deliverable": "", "title": x["text"]})
            entry = {"id": p.stem, "title": g["title"], "status": g["status"], "directives": items}
            pr = goal_pr(path, p.stem, gh)
            if pr:
                entry["pr"], entry["pr_url"] = pr
            if g["status"].lower() == "running":
                ps = goal_plan_state(path, [x["id"] for x in g["directives"]])
                if ps:
                    entry["plan"] = ps
            goals.append(entry)
        except Exception as e:
            errors.append({"where": str(p), "error": f"{type(e).__name__}: {e}"})
    rest = [d for i, d in directives.items() if i not in listed]
    if rest:
        goals.append({"id": None, "title": "", "status": "", "directives": rest})
    try:
        kind = fc.forge(path)["kind"]
    except Exception:
        kind = "none"
    return {"path": str(path), "origin": origin.strip() if origin else None, "forge": kind,
            "branch": branch.strip() if branch else None, "goals": goals}


def collect_runs(path: Path, errors: list) -> list[dict]:
    """The newest RUNS_PER_REPO `runs/<id>/<name>.exit` results of one repo."""
    found = []
    for p in (path / "runs").glob("*/*.exit"):
        try:
            mtime = p.stat().st_mtime
            try:
                code = int(p.read_text().strip().split()[0])
            except (ValueError, IndexError):
                code = None
            found.append({"repo": str(path), "id": p.parent.name, "name": p.stem, "exit": code, "mtime": mtime})
        except OSError as e:
            errors.append({"where": str(p), "error": str(e)})
    return sorted(found, key=lambda r: -r["mtime"])[:RUNS_PER_REPO]


def tmux_argv(*args: str) -> list[str]:
    """A tmux command line; `-S $FRIDAY_TMUX_SOCKET` goes first when that variable is set."""
    sock = os.environ.get("FRIDAY_TMUX_SOCKET")
    return ["tmux", *(["-S", sock] if sock else []), *args]


def collect_sessions(errors: list) -> list[dict]:
    """sessions[] for each `friday-*` tmux session; [] when tmux is absent or has no server."""
    out = _run(tmux_argv("list-panes", "-a", "-F",
                "#{session_name}\t#{session_created}\t#{pane_current_path}\t#{pane_id}"))
    if out is None:
        return []
    sessions, seen = [], set()
    for ln in out.splitlines():
        f = ln.split("\t")
        if len(f) < 4 or not f[0].startswith("friday-") or f[0] in seen:
            continue
        seen.add(f[0])
        created = _num(f[1])
        pane = _run(tmux_argv("capture-pane", "-p", "-t", f[3], "-S", f"-{PANE_LINES}"))
        if pane is None:
            errors.append({"where": f"session {f[0]}", "error": "capture-pane failed"})
            pane = ""
        try:
            sessions.append(session_state(f[0], created, f[2] or None, pane))
        except Exception as e:
            errors.append({"where": f"session {f[0]}", "error": f"{type(e).__name__}: {e}"})
    return sessions


def collect(cwd=None, proc_root: str | Path | None = None, registry_path=None, node_name: str | None = None,
            now: float | None = None) -> dict:
    """The whole snapshot for this node. Never raises for a bad file or a missing tool."""
    cwd = Path(cwd or Path.cwd())
    proc_root = proc_root or os.environ.get("FRIDAY_PROC_ROOT") or "/proc"
    host = socket.gethostname()
    errors: list = []
    reg_node = registry_node(registry_path, node_name, errors)
    snap = empty_snapshot(node_name or (reg_node.name if reg_node else host), host,
                          time.time() if now is None else now)
    snap["errors"] = errors
    paths = find_repos(cwd, registry_path, node_name, errors, node=reg_node)
    snap["health"] = collect_health(proc_root, os.environ.get("FRIDAY_DISK_PATH") or (paths[0] if paths else cwd), errors)
    snap["gpus"] = collect_gpus(errors)
    for p in paths:
        try:
            snap["repos"].append(collect_repo(p, errors))
            snap["runs"] += collect_runs(p, errors)
        except Exception as e:
            errors.append({"where": str(p), "error": f"{type(e).__name__}: {e}"})
    try:
        # list_leases() would mkdir the lease dir; status writes nothing.
        snap["leases"] = fc.list_leases() if fc.lease_dir_path().is_dir() else []
    except Exception as e:
        errors.append({"where": "leases", "error": f"{type(e).__name__}: {e}"})
    snap["sessions"] = collect_sessions(errors)
    return snap
