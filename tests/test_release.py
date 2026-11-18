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
