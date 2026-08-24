"""Shared project config for harness/tools/*.py.

Reads PROJECT_NAME / BIBLIO_CONTACT_EMAIL / BIBLIO_USER_AGENT_TOKEN from the
process environment, falling back to parsing the repo-root
`harness.config.env` (simple KEY=value, no shell features) if a key isn't
already set. No third-party deps (stdlib only), matching the rest of
harness/tools/.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
_CONFIG_PATH = REPO_ROOT / "harness.config.env"


def _load_config_file() -> dict[str, str]:
    if not _CONFIG_PATH.exists():
        return {}
    values: dict[str, str] = {}
    for line in _CONFIG_PATH.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def get(key: str, default: str) -> str:
    import os

    if key in os.environ:
        return os.environ[key]
    return _load_config_file().get(key, default)


PROJECT_NAME = get("PROJECT_NAME", "This Project")
BIBLIO_CONTACT_EMAIL = get("BIBLIO_CONTACT_EMAIL", "")
BIBLIO_USER_AGENT_TOKEN = get("BIBLIO_USER_AGENT_TOKEN", "harness-biblio-tools")


def user_agent() -> str:
    if BIBLIO_CONTACT_EMAIL:
        return f"{BIBLIO_USER_AGENT_TOKEN}/1.0 (mailto:{BIBLIO_CONTACT_EMAIL})"
    return f"{BIBLIO_USER_AGENT_TOKEN}/1.0"
