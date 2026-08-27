"""Shared project config for .friday/active/harness/tools/*.py.

Reads PROJECT_NAME / BIBLIO_CONTACT_EMAIL / BIBLIO_USER_AGENT_TOKEN from the
process environment, falling back to parsing the repo-root
`harness.config.env` (simple KEY=value, no shell features) if a key isn't
already set. No third-party deps (stdlib only), matching the rest of
.friday/active/harness/tools/.
"""

from pathlib import Path

# NOTE: don't derive the consumer repo root from __file__ — this module is
# reached via a symlink (.friday/active/harness/tools/_config.py -> .friday/harness/tools/
# _config.py in a consumer project), and Python sets an imported module's
# __file__ to the resolved real path of whichever sys.path entry found it,
# not the symlink path it was invoked through. Search upward from the
# current working directory instead (these tools are documented to run
# from the repo root, e.g. `python3 .friday/active/harness/tools/verify_references.py`).


def find_repo_root() -> Path:
    """Consumer repo root, found by searching upward from cwd — NOT derived
    from __file__ (see note above: these modules are reached via a symlink,
    and a resolved __file__ points inside .friday/, not the consumer repo).
    These tools are documented to run from the repo root; the upward search
    is a safety net for being invoked from a subdirectory.

    Two separate passes, not one combined `or` check: `.git` is a FILE (not
    a directory) inside a submodule — it holds a `gitdir: <path>` pointer —
    and `Path.exists()` is true for files too. Since these tools now live
    (as generated output) inside .friday/active/harness/tools/, running one
    from cwd somewhere under .friday/ would otherwise stop climbing at
    .friday itself (it has a `.git` file of its own) and never reach the
    real consumer repo root above it — silently, with no error, just every
    REFS_DIR-derived path computed one level too deep. So: walk the WHOLE
    ancestor chain for harness.config.env first (the strongest signal — only
    the consumer repo root ever has one), and only fall back to a second,
    separate walk for `.git` if that comes up empty.
    """
    candidates = (Path.cwd(), *Path.cwd().parents)
    for candidate in candidates:
        if (candidate / "harness.config.env").exists():
            return candidate
    for candidate in candidates:
        if (candidate / ".git").exists():
            return candidate
    return Path.cwd()


def _find_config_path() -> Path | None:
    for candidate in (Path.cwd(), *Path.cwd().parents):
        path = candidate / "harness.config.env"
        if path.exists():
            return path
    return None


def _load_config_file() -> dict[str, str]:
    config_path = _find_config_path()
    if config_path is None:
        return {}
    values: dict[str, str] = {}
    for line in config_path.read_text().splitlines():
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
