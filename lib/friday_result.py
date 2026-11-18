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
