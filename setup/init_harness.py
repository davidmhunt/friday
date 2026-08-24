#!/usr/bin/env python3
"""Drop-in setup / sync script for the "friday" portable agent harness.

Run from a consumer project's repo root, after adding this repo as a git
submodule at `.friday/`:

    git submodule add <url> .friday && git submodule update --init --recursive
    python3 .friday/setup/init_harness.py

Fresh drop-in: runs an interactive interview, writes `harness.config.env`
at the repo root, then creates the symlink tree and materializes templated
files per `MANIFEST.json`.

Re-run (config already exists): re-syncs symlinks and reports what a fresh
render of each templated file would produce, WITHOUT overwriting an
existing materialized file (a project may have hand-edited it beyond the
interview answers). Pass --reconfigure to re-run the interview with
existing answers as defaults. Pass --force-materialize=<path> (repeatable)
to overwrite one specific materialized file with a fresh render.

Stdlib only — no third-party dependency, matches the rest of this repo's
tooling philosophy.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path.cwd()
SUBMODULE_DIR = REPO_ROOT / ".friday"
CONFIG_PATH = REPO_ROOT / "harness.config.env"
MANIFEST_PATH = SUBMODULE_DIR / "MANIFEST.json"

PLACEHOLDER_RE = re.compile(r"\[SET AT SETUP:\s*([A-Z0-9_]+)(?:[^\]]*)\]")
SECTION_RE = re.compile(
    r"<!--\s*SECTION:([a-zA-Z0-9_]+):start\s*-->.*?<!--\s*SECTION:\1:end\s*-->\n?",
    re.DOTALL,
)

# ---------------------------------------------------------------------------
# Config file I/O
# ---------------------------------------------------------------------------


def load_config() -> dict[str, str]:
    if not CONFIG_PATH.exists():
        return {}
    values: dict[str, str] = {}
    for line in CONFIG_PATH.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def write_config(values: dict[str, str]) -> None:
    lines = ["# Written by .friday/setup/init_harness.py — non-secret structural config.",
             "# Secrets (tokens, API keys) belong in .env, not here.", ""]
    for key, value in values.items():
        lines.append(f"{key}={value}")
    CONFIG_PATH.write_text("\n".join(lines) + "\n")
    print(f"Wrote {CONFIG_PATH}")


# ---------------------------------------------------------------------------
# Interview
# ---------------------------------------------------------------------------


def ask(prompt: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    answer = input(f"{prompt}{suffix}: ").strip()
    return answer or (default or "")


def ask_yn(prompt: str, default: bool = True) -> bool:
    suffix = " [Y/n]" if default else " [y/N]"
    answer = input(f"{prompt}{suffix}: ").strip().lower()
    if not answer:
        return default
    return answer.startswith("y")


def run_interview(existing: dict[str, str]) -> dict[str, str]:
    print("\n=== friday harness setup interview ===\n")
    cfg = dict(existing)
    cfg["PROJECT_NAME"] = ask("Project name", existing.get("PROJECT_NAME") or REPO_ROOT.name)
    cfg["PROJECT_NAME_LOWER"] = re.sub(r"[^a-z0-9]+", "-", cfg["PROJECT_NAME"].lower()).strip("-")
    cfg["PROJECT_WORKING_ROOT"] = ask("Absolute working root path", existing.get("PROJECT_WORKING_ROOT") or str(REPO_ROOT))
    cfg["PACKAGE_MANAGER"] = ask("Package manager (e.g. uv, pip, poetry, npm)", existing.get("PACKAGE_MANAGER", "uv"))
    cfg["PACKAGE_MANAGER_SYNC_CMD"] = ask("Sync/install command", existing.get("PACKAGE_MANAGER_SYNC_CMD", f"{cfg['PACKAGE_MANAGER']} sync"))
    cfg["PACKAGE_MANAGER_RUN_CMD"] = ask("Run command prefix", existing.get("PACKAGE_MANAGER_RUN_CMD", f"{cfg['PACKAGE_MANAGER']} run"))
    cfg["PACKAGE_MANAGER_ADD_CMD"] = ask("Add-dependency command", existing.get("PACKAGE_MANAGER_ADD_CMD", f"{cfg['PACKAGE_MANAGER']} add"))
    cfg["TEST_CMD"] = ask("Test command", existing.get("TEST_CMD", f"{cfg['PACKAGE_MANAGER_RUN_CMD']} pytest"))
    cfg["DEPENDENCY_MANIFEST"] = ask("Dependency manifest file", existing.get("DEPENDENCY_MANIFEST", "pyproject.toml"))
    cfg["LOCKFILE"] = ask("Lockfile", existing.get("LOCKFILE", "uv.lock"))

    print("\nLaunch method for detached background jobs:")
    print("  1) systemd-run-user   (a user systemd manager is available)")
    print("  2) setsid-nohup       (bare SSH box, no systemd user manager)")
    print("  3) setsid-nohup-container (running inside the project's Docker container)")
    choice = ask("Choice", {"systemd-run-user": "1", "setsid-nohup": "2", "setsid-nohup-container": "3"}.get(existing.get("LAUNCH_METHOD", ""), "1"))
    cfg["LAUNCH_METHOD"] = {"1": "systemd-run-user", "2": "setsid-nohup", "3": "setsid-nohup-container"}.get(choice, "systemd-run-user")

    cfg["VCS_REMOTE"] = ask("Git remote (SSH URL)", existing.get("VCS_REMOTE", ""))

    print("\nTask tracker:")
    print("  1) none  2) gitlab-issues  3) github-issues")
    tchoice = ask("Choice", {"none": "1", "gitlab-issues": "2", "github-issues": "3"}.get(existing.get("TRACKER_KIND", ""), "1"))
    cfg["TRACKER_KIND"] = {"1": "none", "2": "gitlab-issues", "3": "github-issues"}.get(tchoice, "none")
    if cfg["TRACKER_KIND"] != "none":
        cfg["TRACKER_HOST"] = ask("Tracker host", existing.get("TRACKER_HOST", "gitlab.com" if cfg["TRACKER_KIND"] == "gitlab-issues" else "github.com"))
        cfg["VCS_REMOTE_PROJECT_PATH"] = ask("Project path (org/repo)", existing.get("VCS_REMOTE_PROJECT_PATH", ""))

    adapters = []
    if ask_yn("Enable the Claude Code adapter (.claude/)?", True):
        adapters.append("claude")
    if ask_yn("Enable the Antigravity adapter (.agents/)?", True):
        adapters.append("antigravity")
    cfg["ADAPTERS_ENABLED"] = ",".join(adapters)

    cfg["HIGH_TIER_MODEL_KEYWORDS"] = ask("High-tier model keyword(s), comma-separated", existing.get("HIGH_TIER_MODEL_KEYWORDS", "opus"))
    cfg["BIBLIO_CONTACT_EMAIL"] = ask("Contact email for bibliography-tool User-Agent (blank to skip)", existing.get("BIBLIO_CONTACT_EMAIL", ""))
    cfg["BIBLIO_USER_AGENT_TOKEN"] = ask("User-Agent product token for bibliography tools", existing.get("BIBLIO_USER_AGENT_TOKEN", f"{cfg['PROJECT_NAME'].lower().replace(' ', '-')}-biblio-tools"))

    # --- Docker (B.1a) ---
    cfg["DOCKER_ENABLED"] = "true" if ask_yn("\nSet up Docker for this project?", False) else "false"
    if cfg["DOCKER_ENABLED"] == "true":
        volumes = []
        print("Additional host volumes to mount (host_path:container_path[:ro]), blank line to finish:")
        while True:
            v = input("  volume> ").strip()
            if not v:
                break
            volumes.append(v)
        cfg["DOCKER_EXTRA_VOLUMES"] = ";".join(volumes)
        cfg["DOCKER_BUILD_NOW"] = "true" if ask_yn("Build the image now?", False) else "false"

    return cfg


# ---------------------------------------------------------------------------
# Placeholder rendering
# ---------------------------------------------------------------------------


LAUNCH_METHOD_SECTIONS = {
    "systemd-run-user": "launch_systemd",
    "setsid-nohup": "launch_setsid",
    "setsid-nohup-container": "launch_container",
}
TRACKER_KIND_SECTIONS = {
    "none": "tracker_none",
    "gitlab-issues": "tracker_gitlab",
    "github-issues": "tracker_github",
}


def sections_to_drop(cfg: dict[str, str]) -> set[str]:
    """Config-driven section drops: the LAUNCH_METHOD/TRACKER_KIND variants
    that don't match this project's choice are removed automatically. Other
    SECTION markers (accelerator notes, optional prose blocks) are left for
    the operator to delete by hand — there's no config key to decide those.
    """
    drop = set()
    keep_launch = LAUNCH_METHOD_SECTIONS.get(cfg.get("LAUNCH_METHOD", ""))
    for name in LAUNCH_METHOD_SECTIONS.values():
        if name != keep_launch:
            drop.add(name)
    keep_tracker = TRACKER_KIND_SECTIONS.get(cfg.get("TRACKER_KIND", "none"))
    for name in TRACKER_KIND_SECTIONS.values():
        if name != keep_tracker:
            drop.add(name)
    return drop


def render(text: str, cfg: dict[str, str], drop_sections: set[str]) -> str:
    def drop_section(m: re.Match) -> str:
        name = m.group(1)
        return "" if name in drop_sections else m.group(0)

    text = SECTION_RE.sub(drop_section, text)

    def sub_token(m: re.Match) -> str:
        key = m.group(1)
        return cfg.get(key, m.group(0))

    return PLACEHOLDER_RE.sub(sub_token, text)


# ---------------------------------------------------------------------------
# Symlinks + materialization
# ---------------------------------------------------------------------------


def adapter_of(entry: dict) -> str | None:
    return entry.get("adapter")


def sync_symlinks(manifest: dict, cfg: dict[str, str], dry_run: bool) -> None:
    enabled_adapters = set(cfg.get("ADAPTERS_ENABLED", "claude,antigravity").split(","))
    docker_enabled = cfg.get("DOCKER_ENABLED", "false") == "true"
    for entry in manifest["symlinks"]:
        adapter = adapter_of(entry)
        if adapter and adapter not in enabled_adapters:
            continue
        if entry.get("docker") and not docker_enabled:
            continue
        src = (SUBMODULE_DIR / entry["src"]).resolve()
        dest = REPO_ROOT / entry["dest"]
        if not src.exists():
            print(f"  WARN: symlink source missing: {src}")
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        rel_target = os.path.relpath(src, dest.parent)
        if dest.is_symlink():
            if os.readlink(dest) == rel_target:
                continue
            print(f"  relink {dest} -> {rel_target}")
            if not dry_run:
                dest.unlink()
                dest.symlink_to(rel_target)
        elif dest.exists():
            print(f"  REFUSE (real file exists, not overwriting): {dest}")
        else:
            print(f"  symlink {dest} -> {rel_target}")
            if not dry_run:
                dest.symlink_to(rel_target)


def materialize_files(manifest: dict, cfg: dict[str, str], dry_run: bool, force: set[str]) -> None:
    docker_enabled = cfg.get("DOCKER_ENABLED", "false") == "true"
    for entry in manifest["materialize"]:
        adapter = adapter_of(entry)
        enabled_adapters = set(cfg.get("ADAPTERS_ENABLED", "claude,antigravity").split(","))
        if adapter and adapter not in enabled_adapters:
            continue
        if entry.get("docker") and not docker_enabled:
            continue
        src = SUBMODULE_DIR / entry["src"]
        dest = REPO_ROOT / entry["dest"]
        if not src.exists():
            print(f"  WARN: template source missing: {src}")
            continue
        rendered = render(src.read_text(), cfg, drop_sections=sections_to_drop(cfg))
        if dest.exists() and str(dest) not in force:
            if dest.read_text() != rendered:
                print(f"  SKIP (already materialized, differs from fresh render — use --force-materialize={dest} to overwrite): {dest}")
            continue
        print(f"  {'overwrite' if dest.exists() else 'materialize'} {dest}")
        if not dry_run:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(rendered)
            if src.name in ("pre-commit", "commit-msg") or os.access(src, os.X_OK):
                dest.chmod(dest.stat().st_mode | stat.S_IEXEC)


def install_git_hooks(manifest: dict, dry_run: bool) -> None:
    anchor = manifest["git_hooks"]["anchor"]
    for hook in manifest["git_hooks"]["hooks"]:
        dest = REPO_ROOT / ".git" / "hooks" / hook
        target = f"../../{anchor}/{hook}"
        if dest.is_symlink() and os.readlink(dest) == target:
            continue
        print(f"  git hook {dest} -> {target}")
        if not dry_run:
            if dest.exists() or dest.is_symlink():
                dest.unlink()
            dest.symlink_to(target)


# ---------------------------------------------------------------------------
# Docker
# ---------------------------------------------------------------------------


def apply_docker_volumes(cfg: dict[str, str]) -> None:
    compose_path = REPO_ROOT / "docker-compose.yml"
    if not compose_path.exists():
        return
    extra = [v for v in cfg.get("DOCKER_EXTRA_VOLUMES", "").split(";") if v]
    text = compose_path.read_text()
    block_re = re.compile(
        r"(?P<indent>[ \t]*)# --- user-added volumes \(managed by init_harness\.py\) ---\n"
        r"(?P<body>.*?)"
        r"(?P=indent)# --- end user-added volumes ---",
        re.DOTALL,
    )

    def replace(m: re.Match) -> str:
        indent = m.group("indent")
        lines = "".join(f"{indent}- {v}\n" for v in extra)
        return (
            f"{indent}# --- user-added volumes (managed by init_harness.py) ---\n"
            f"{lines}"
            f"{indent}# --- end user-added volumes ---"
        )

    if block_re.search(text):
        text = block_re.sub(replace, text)
    compose_path.write_text(text)
    print(f"  wrote {len(extra)} extra volume(s) into {compose_path}")


def maybe_build_docker(cfg: dict[str, str], dry_run: bool) -> None:
    if cfg.get("DOCKER_BUILD_NOW") != "true":
        return
    print("  running: docker compose build")
    if dry_run:
        return
    try:
        subprocess.run(["docker", "compose", "build"], cwd=REPO_ROOT, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"  WARN: docker compose build failed: {e}")


DOCKER_MANUAL_SECTION_MARKER = "<!-- SECTION:docker_quickstart:start -->"


def write_user_guide_docker_section(cfg: dict[str, str], dry_run: bool) -> None:
    guide = REPO_ROOT / "harness" / "USER_GUIDE.md"
    if not guide.exists():
        return
    if cfg.get("DOCKER_ENABLED") == "true":
        content = (
            "```bash\n"
            "docker compose build\n"
            "docker compose up -d\n"
            "docker compose exec harness bash\n"
            "```\n"
        )
    else:
        content = (
            "Docker was not set up automatically for this project. To set it up "
            "by hand: copy `.friday/docker/{Dockerfile,.dockerignore}` and render "
            "`.friday/docker/docker-compose.yml.tmpl` to `docker-compose.yml` at the "
            "repo root (fill in the `[SET AT SETUP: ...]` tokens by hand), then:\n\n"
            "```bash\n"
            "docker compose build\n"
            "docker compose up -d\n"
            "docker compose exec harness bash\n"
            "```\n\n"
            "Before starting the container, run `ssh-add` on the host so the "
            "container's forwarded SSH agent can authenticate to your git remote.\n\n"
            "To add a volume by hand, edit the `# --- user-added volumes ---` block "
            "in `docker-compose.yml` — the same block `init_harness.py --reconfigure` "
            "manages, so manual edits and future re-runs don't fight each other.\n"
        )
    text = guide.read_text()
    section_re = re.compile(
        r"## Setting up Docker manually\n\n.*?(?=\n## |\Z)", re.DOTALL
    )
    new_section = f"## Setting up Docker manually\n\n{content}"
    if section_re.search(text):
        text = section_re.sub(new_section, text)
    else:
        text = text.rstrip("\n") + "\n\n" + new_section
    print(f"  refreshed 'Setting up Docker manually' section in {guide}")
    if not dry_run:
        guide.write_text(text)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def preflight() -> None:
    if not (REPO_ROOT / ".gitmodules").exists() or not SUBMODULE_DIR.exists():
        print(
            "No .friday/ submodule found. Add it first:\n\n"
            "  git submodule add <url> .friday\n"
            "  git submodule update --init --recursive\n"
        )
        sys.exit(1)
    if not MANIFEST_PATH.exists():
        print(f"MANIFEST.json not found at {MANIFEST_PATH} — submodule checkout looks incomplete.")
        sys.exit(1)


def closing_checklist(cfg: dict[str, str]) -> None:
    print("\n=== Closing checklist ===")
    leftovers = []
    for path in (REPO_ROOT / "harness").rglob("*.md"):
        if PLACEHOLDER_RE.search(path.read_text(errors="ignore")):
            leftovers.append(path)
    for path in (REPO_ROOT / "AGENTS.md", REPO_ROOT / "README.md"):
        if path.exists() and PLACEHOLDER_RE.search(path.read_text(errors="ignore")):
            leftovers.append(path)
    if leftovers:
        print(f"  [ ] {len(leftovers)} file(s) still have [SET AT SETUP: ...] markers — fill in by hand:")
        for p in leftovers:
            print(f"        {p.relative_to(REPO_ROOT)}")
    else:
        print("  [x] no leftover [SET AT SETUP: ...] markers")
    hooks_ok = all((REPO_ROOT / ".git" / "hooks" / h).is_symlink() for h in ("pre-commit", "commit-msg"))
    print(f"  [{'x' if hooks_ok else ' '}] .git/hooks/{{pre-commit,commit-msg}} installed")
    for adapter, dirname in (("claude", ".claude"), ("antigravity", ".agents")):
        enabled = adapter in cfg.get("ADAPTERS_ENABLED", "").split(",")
        present = (REPO_ROOT / dirname / "agents").exists()
        ok = enabled == present
        print(f"  [{'x' if ok else ' '}] {dirname}/ present={present} matches ADAPTERS_ENABLED={enabled}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reconfigure", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force-materialize", action="append", default=[])
    args = parser.parse_args()

    preflight()
    manifest = json.loads(MANIFEST_PATH.read_text())
    existing = load_config()

    if not existing or args.reconfigure:
        cfg = run_interview(existing)
        if not args.dry_run:
            write_config(cfg)
    else:
        cfg = existing
        print("Existing harness.config.env found — re-syncing (pass --reconfigure to re-run the interview).")

    print("\n=== Symlinks ===")
    sync_symlinks(manifest, cfg, args.dry_run)

    print("\n=== Materialized files ===")
    materialize_files(manifest, cfg, args.dry_run, force=set(args.force_materialize))

    print("\n=== Git hooks ===")
    install_git_hooks(manifest, args.dry_run)

    if cfg.get("DOCKER_ENABLED") == "true":
        print("\n=== Docker ===")
        if not args.dry_run:
            apply_docker_volumes(cfg)
            maybe_build_docker(cfg, args.dry_run)

    print("\n=== USER_GUIDE.md Docker section ===")
    write_user_guide_docker_section(cfg, args.dry_run)

    closing_checklist(cfg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
