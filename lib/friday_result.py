"""friday result: record an expensive run once in a tracked file results/<id>.json.

The record holds the metrics, each file's sha256 and size, the command, the HEAD commit, whether
tracked files were modified (dirty), the node name and the time. Recorded files may be untracked
(datasets, checkpoints under runs/); only the record is tracked.
"""
from __future__ import annotations

import hashlib
import json
import socket
import time
from pathlib import Path

import friday_core as fc
import friday_fleet as ff

RESULT_DIR = Path("results")


class ResultError(Exception):
    pass


def result_path(root: Path, did: str) -> Path:
    return Path(root) / RESULT_DIR / f"{did}.json"


def node_name() -> str:
    """This node's name: the identity file's name, else the hostname."""
    try:
        nf = ff.load_node_file()
    except ff.RegistryError:
        nf = None
    return nf[0] if nf else socket.gethostname()


def parse_metric(text: str):
    """`K=V` -> (key, number or string). Ints and floats become numbers."""
    key, sep, val = text.partition("=")
    key = key.strip()
    if not sep or not key:
        raise ResultError(f"bad --metric {text!r}: expected K=V")
    val = val.strip()
    for conv in (int, float):
        try:
            return key, conv(val)
        except ValueError:
            pass
    return key, val


def file_entry(root: Path, path: str) -> dict:
    p = Path(path)
    full = p if p.is_absolute() else Path(root) / p
    if not full.is_file():
        raise ResultError(f"file not found: {path}")
    try:
        rel = str(full.resolve().relative_to(Path(root).resolve()))
    except ValueError:
        rel = str(full.resolve())
    h = hashlib.sha256()
    with open(full, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return {"path": rel, "sha256": h.hexdigest(), "size": full.stat().st_size}


def build(root: Path, did: str, metrics=(), files=(), cmd: str = "", note: str = "",
          now: float | None = None) -> dict:
    root = Path(root)
    commit = fc._git(["rev-parse", "HEAD"], root)
    if not commit:
        raise ResultError("no HEAD commit to record")
    dirty = bool(fc._git(["status", "--porcelain", "--untracked-files=no", "--", ".", ":(exclude)results"], root))
    m = {}
    for t in metrics:
        k, v = parse_metric(t)
        m[k] = v
    t = time.time() if now is None else now
    return {
        "id": did,
        "metrics": m,
        "files": [file_entry(root, f) for f in files],
        "cmd": cmd,
        "note": note,
        "commit": commit,
        "dirty": dirty,
        "node": node_name(),
        "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t)),
    }


def write(root: Path, did: str, **kw) -> Path:
    rec = build(root, did, **kw)
    p = result_path(root, did)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rec, indent=2, sort_keys=True) + "\n")
    return p


_OPS = {
    ">=": lambda a, b: a >= b, "<=": lambda a, b: a <= b, "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b, ">": lambda a, b: a > b, "<": lambda a, b: a < b,
}


def _num(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return v
    try:
        return float(str(v).strip())
    except ValueError:
        return None


def check_require(metrics: dict, expr: str) -> str | None:
    """None when `K OP V` holds, else a one-line reason."""
    parts = expr.split(None, 2)
    if len(parts) != 3 or parts[1] not in _OPS:
        return f"bad --require {expr!r}: expected 'K OP V' with OP one of >= > <= < == !="
    k, op, want = parts
    if k not in metrics:
        return f"metric {k} is not recorded (required {k} {op} {want})"
    have = metrics[k]
    a, b = _num(have), _num(want)
    if a is None or b is None:
        a, b = str(have), want
    if not _OPS[op](a, b):
        return f"requirement failed: {k} {op} {want} (recorded {k} = {have})"
    return None


def check(root: Path, did: str, requires=(), files: bool = False) -> list[str]:
    """Return one line per failed condition; empty means the check passes."""
    root = Path(root)
    p = result_path(root, did)
    if not p.is_file():
        return [f"no record {RESULT_DIR / (did + '.json')}: run `friday result write {did}`"]
    try:
        rec = json.loads(p.read_text())
        commit = rec["commit"]
    except (ValueError, KeyError, TypeError):
        return [f"record {RESULT_DIR / (did + '.json')} is not a valid result record"]
    fails = []
    if fc._git(["merge-base", "--is-ancestor", str(commit), "HEAD"], root) is None:
        fails.append(f"record commit {str(commit)[:12]} is not an ancestor of HEAD")
    metrics = rec.get("metrics") or {}
    for expr in requires:
        msg = check_require(metrics, expr)
        if msg:
            fails.append(msg)
    if files:
        for f in rec.get("files") or []:
            path = Path(f["path"])
            full = path if path.is_absolute() else root / path
            if not full.is_file():
                continue  # absent files are not checked
            h = hashlib.sha256()
            with open(full, "rb") as fh:
                for chunk in iter(lambda: fh.read(1 << 20), b""):
                    h.update(chunk)
            if h.hexdigest() != f.get("sha256"):
                fails.append(f"file changed: {f['path']} no longer has its recorded sha256")
    return fails
