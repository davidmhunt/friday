"""Release consistency: version, changelog, marketplace entry, licence, README."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _plugin():
    return json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())


def test_version_matches_top_released_changelog_heading():
    headings = re.findall(r"^## (\S+) - \d{4}-\d{2}-\d{2}\s*$",
                          (ROOT / "CHANGELOG.md").read_text(), re.M)
    assert headings, "CHANGELOG.md has no released heading"
    assert _plugin()["version"] == headings[0]


def test_marketplace_names_the_plugin():
    mp = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text())
    assert _plugin()["name"] in [p["name"] for p in mp["plugins"]]


def test_license_exists():
    assert (ROOT / "LICENSE").is_file()


def test_readme_has_no_alpha():
    assert "alpha" not in (ROOT / "README.md").read_text().lower()


_INSTALL_RE = re.compile(
    r"^(git clone .*|/plugin marketplace add .*|/plugin install .*|python3 \S*bin/friday install\b.*)$",
    re.M)


def _install_commands(path):
    return [re.sub(r"\s+#.*$", "", m.group(0)).strip()
            for m in _INSTALL_RE.finditer((ROOT / path).read_text())]


def test_readme_and_tutorial_share_install_commands():
    readme = _install_commands("README.md")
    tutorial = _install_commands("docs/getting-started.md")
    assert len(readme) == 4, readme
    assert readme == tutorial
    assert [c.split()[0] for c in readme] == [
        "git", "/plugin", "/plugin", "python3"]


def test_path_step_is_not_conditional():
    for path in ("README.md", "docs/getting-started.md"):
        text = (ROOT / path).read_text().lower()
        assert "if you cloned" not in text, path
        assert "bin/friday install" in text, path
