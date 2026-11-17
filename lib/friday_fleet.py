"""Node registry for friday's fleet dispatch. Standard library only.

Registry file (TOML), first existing of: $FRIDAY_NODES, <plugin root>/nodes.toml,
~/.config/friday/nodes.toml. Top-level `report_to` (optional) and `[node.<name>]` tables.
"""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
ROLES = ("master", "worker", "target")
RUNTIMES = ("container", "native")
LAUNCHERS = ("tmux",)


class RegistryError(ValueError):
    """The nodes file is missing, unparsable, or invalid."""


@dataclass
class Node:
    name: str
    role: str
    ssh: str
    runtime: str = "native"
    tags: list = field(default_factory=list)
    repos: str = ""
    plugin_dir: str = ""
    launcher: str = "tmux"


@dataclass
class Registry:
    path: Path
    report_to: str | None
    nodes: dict  # name -> Node, in file order


def find_nodes_file() -> Path | None:
    cands = []
    env = os.environ.get("FRIDAY_NODES")
    if env:
        cands.append(Path(env).expanduser())
    cands.append(PLUGIN_ROOT / "nodes.toml")
    cands.append(Path.home() / ".config" / "friday" / "nodes.toml")
    for c in cands:
        if c.is_file():
            return c
    return None


def _str(name: str, key: str, val) -> str:
    if not isinstance(val, str) or not val.strip():
        raise RegistryError(f"node '{name}': '{key}' must be a non-empty string")
    return val


def load_nodes(path) -> Registry:
    path = Path(path)
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except OSError as e:
        raise RegistryError(f"cannot read {path}: {e}") from e
    except tomllib.TOMLDecodeError as e:
        raise RegistryError(f"{path}: invalid TOML: {e}") from e

    report_to = data.get("report_to")
    if report_to is not None and not isinstance(report_to, str):
        raise RegistryError("'report_to' must be a string")
    table = data.get("node")
    if not isinstance(table, dict) or not table:
        raise RegistryError(f"{path}: no [node.<name>] tables")

    nodes: dict = {}
    seen_ssh: dict = {}
    for name, raw in table.items():
        if not isinstance(raw, dict):
            raise RegistryError(f"node '{name}': must be a table")
        if "ssh" not in raw:
            raise RegistryError(f"node '{name}': missing key 'ssh'")
        ssh = _str(name, "ssh", raw["ssh"])
        if ssh in seen_ssh:
            raise RegistryError(
                f"node '{name}': duplicate 'ssh' {ssh!r} (already used by '{seen_ssh[ssh]}')")
        seen_ssh[ssh] = name
        role = raw.get("role")
        if role not in ROLES:
            raise RegistryError(
                f"node '{name}': unknown 'role' {role!r} (expected one of {', '.join(ROLES)})")
        runtime = raw.get("runtime", "native")
        if runtime not in RUNTIMES:
            raise RegistryError(
                f"node '{name}': unknown 'runtime' {runtime!r} (expected one of {', '.join(RUNTIMES)})")
        launcher = raw.get("launcher", "tmux")
        if launcher not in LAUNCHERS:
            raise RegistryError(
                f"node '{name}': unknown 'launcher' {launcher!r} (expected one of {', '.join(LAUNCHERS)})")
        tags = raw.get("tags", [])
        if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
            raise RegistryError(f"node '{name}': 'tags' must be a list of strings")
        repos = raw.get("repos", "")
        plugin_dir = raw.get("plugin_dir", "")
        if role in ("master", "worker"):
            for key, val in (("repos", repos), ("plugin_dir", plugin_dir)):
                if not val:
                    raise RegistryError(f"node '{name}': {role} needs key '{key}'")
                _str(name, key, val)
        nodes[name] = Node(name, role, ssh, runtime, list(tags), repos, plugin_dir, launcher)
    return Registry(path, report_to, nodes)
