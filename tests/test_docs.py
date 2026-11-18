"""The docs must mention every registry key and every friday subcommand."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = (ROOT / "docs" / "fleet.md").read_text() + "\n" + (ROOT / "README.md").read_text()


def _registry_keys():
    src = (ROOT / "lib" / "friday_fleet.py").read_text()
    body = src[src.index("def load_nodes"):src.index("class RouteError")]
    keys = set(re.findall(r'\b(?:raw|data)(?:\.get\(|\[)\s*"(\w+)"', body))
    return keys | set(re.findall(r'\(\("(\w+)", \w+\)', body))


def _subcommands():
    src = (ROOT / "bin" / "friday").read_text()
    return set(re.findall(r'sub\.add_parser\("([\w-]+)"\)', src))


def test_extraction_finds_things():
    assert {"ssh", "role", "runtime", "tags", "repos", "plugin_dir", "launcher", "report_to"} <= _registry_keys()
    assert {"status", "dispatch", "nodes", "land"} <= _subcommands()


def test_every_registry_key_documented():
    missing = [k for k in sorted(_registry_keys()) if not re.search(rf"\b{k}\b", DOCS)]
    assert not missing, f"undocumented nodes.toml keys: {missing}"


def test_every_subcommand_documented():
    missing = [c for c in sorted(_subcommands()) if not re.search(rf"`{c}`|friday {c}\b", DOCS)]
    assert not missing, f"undocumented subcommands: {missing}"
