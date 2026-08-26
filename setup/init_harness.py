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
# Broader than PLACEHOLDER_RE: also catches free-text prose markers (e.g.
# "[SET AT SETUP: describe ...]") that PLACEHOLDER_RE's all-caps capture
# group deliberately doesn't match (those aren't tokens render() substitutes
# — they're for a human/agent to write prose into by hand). Used only for
# the closing-checklist leftover scan, never for substitution.
LEFTOVER_RE = re.compile(r"\[SET AT SETUP:[^\]]*\]")
# The optional `(?:^[ \t]*#[ \t]*)?` before each marker lets a source file
# whose native comment syntax is '#' (Dockerfile, docker-compose.yml,
# entrypoint.sh — none of which tolerate a bare HTML comment) write its
# markers as e.g. `# <!-- SECTION:name:start -->`: when KEPT, that '#'
# prefix is part of the match and comes back out verbatim (still a valid
# comment); when DROPPED, it's removed along with everything else instead
# of being left behind as an orphaned '#' merged into the next line. Plain
# `<!-- SECTION:... -->` markers (no '#' prefix, the .md.tmpl convention)
# still match exactly as before — the whole group is optional.
SECTION_RE = re.compile(
    r"(?:^[ \t]*#[ \t]*)?<!--\s*SECTION:([a-zA-Z0-9_]+):start\s*-->"
    r".*?"
    r"(?:^[ \t]*#[ \t]*)?<!--\s*SECTION:\1:end\s*-->\n?",
    re.DOTALL | re.MULTILINE,
)
# Same gating idea as SECTION_RE, but for files that can't carry HTML
# comments (.gitignore, .gitattributes) — uses '#' comment markers instead.
# Used only by sync_git_ignore_attributes().
GATE_RE = re.compile(
    r"#\s*GATE:([a-zA-Z0-9_]+):start\s*\n(.*?)#\s*GATE:\1:end\s*\n?",
    re.DOTALL,
)
GIT_MANAGED_BLOCK_RE = re.compile(
    r"# --- friday harness \(managed by init_harness\.py\) ---\n"
    r".*?"
    r"# --- end friday harness ---\n?",
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

    cfg["LATEX_DRAFTING_ENABLED"] = "true" if ask_yn(
        "\nUse the LaTeX/Beamer drafting suite (Researcher drafts formal theory\n"
        "in docs/theory/, Author builds the final report + slide decks in\n"
        "docs/report/, both as self-contained latexmk projects)?", False
    ) else "false"
    if cfg["LATEX_DRAFTING_ENABLED"] != "true":
        print(
            "  Researcher/Author still keep their other duties (memos, references,\n"
            "  docs/RESULTS.md) — they just won't reference docs/theory/ or\n"
            "  docs/report/, and any formal writeup goes into a Markdown doc instead."
        )

    cfg["ACCELERATORS_ENABLED"] = "true" if ask_yn("\nDoes this project use GPU/accelerator hardware?", False) else "false"
    if cfg["ACCELERATORS_ENABLED"] == "true":
        print(
            "  After this interview, fill in the device table and allocation policy\n"
            "  in harness/rules/gpu.md (materialized from harness/rules/gpu.md.tmpl) —\n"
            "  those are free-text [SET AT SETUP: ...] prose blocks the script can't\n"
            "  infer, same as the Project Overview section in AGENTS.md."
        )

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
ACCELERATOR_SECTIONS = {
    "false": "accel_none",
    "true": "accel_present",
}
LATEX_SECTIONS = {
    "false": "latex_off",
    "true": "latex_on",
}


def sections_to_drop(cfg: dict[str, str]) -> set[str]:
    """Config-driven section drops: the LAUNCH_METHOD/TRACKER_KIND/
    ACCELERATORS_ENABLED/LATEX_DRAFTING_ENABLED variants that don't match
    this project's choice are removed automatically. Other SECTION markers
    (optional prose blocks) are
    left for the operator to delete by hand — there's no config key to
    decide those.
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
    keep_accel = ACCELERATOR_SECTIONS.get(cfg.get("ACCELERATORS_ENABLED", "false"))
    for name in ACCELERATOR_SECTIONS.values():
        if name != keep_accel:
            drop.add(name)
    # environment.md.tmpl's single free-text accelerator note: drop it
    # outright when there's no accelerator, keep (for the agent to fill in)
    # when there is.
    if cfg.get("ACCELERATORS_ENABLED", "false") != "true":
        drop.add("accelerator")
    keep_latex = LATEX_SECTIONS.get(cfg.get("LATEX_DRAFTING_ENABLED", "false"))
    for name in LATEX_SECTIONS.values():
        if name != keep_latex:
            drop.add(name)
    # README.md.tmpl's Docker quickstart block: only meaningful when this
    # project actually has Docker set up.
    if cfg.get("DOCKER_ENABLED", "false") != "true":
        drop.add("docker_quickstart")
    # version_control.md.tmpl's LFS-policy bullet: LFS-tracked PDFs only
    # arise from the LaTeX/Beamer drafting suite (docs/theory/, docs/report/).
    if cfg.get("LATEX_DRAFTING_ENABLED", "false") != "true":
        drop.add("lfs_policy")
    # Dockerfile.tmpl / entrypoint.sh.tmpl / docker-compose.yml.tmpl: which
    # package-manager install and agent-CLI install blocks are relevant is
    # entirely config-driven, derived from PACKAGE_MANAGER and
    # ADAPTERS_ENABLED (already answered in earlier interview sections) —
    # no separate Docker-specific question is asked for any of this.
    package_manager = cfg.get("PACKAGE_MANAGER", "").strip().lower()
    adapters_enabled = {
        a.strip() for a in cfg.get("ADAPTERS_ENABLED", "").split(",") if a.strip()
    }
    pm_uv = package_manager == "uv"
    pm_poetry = package_manager == "poetry"
    pm_pip = package_manager in ("pip", "pip3")
    pm_node = package_manager in ("npm", "pnpm", "yarn")
    pm_none = not (pm_uv or pm_poetry or pm_pip or pm_node)
    agent_claude = "claude" in adapters_enabled
    agent_antigravity = "antigravity" in adapters_enabled
    if not (pm_node or agent_claude):
        drop.add("docker_node_runtime")
    if not pm_uv:
        drop.add("docker_pm_uv")
    if not pm_poetry:
        drop.add("docker_pm_poetry")
    if not pm_pip:
        drop.add("docker_pm_pip")
    if not pm_node:
        drop.add("docker_pm_node")
    if not pm_none:
        drop.add("docker_pm_none")
    # Two gates per adapter, one per file: `docker_agent_<x>` covers the
    # Dockerfile's install + home-directory pre-creation, `..._compose` covers
    # everything that adapter contributes to docker-compose.yml (its config
    # volume, and any environment variables only its tooling reads). Claude
    # gets exactly the same treatment as Antigravity here — it previously had
    # an ungated config volume, so an antigravity-only project still got a
    # claude-config volume it could never use.
    if not agent_claude:
        drop.add("docker_agent_claude")
        drop.add("docker_agent_claude_compose")
    if not agent_antigravity:
        drop.add("docker_agent_antigravity")
        drop.add("docker_agent_antigravity_compose")
    if cfg.get("LATEX_DRAFTING_ENABLED", "false") != "true":
        drop.add("docker_latex")
    if cfg.get("ACCELERATORS_ENABLED", "false") != "true":
        drop.add("docker_gpu")
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
    # --force-materialize accepts either an absolute path or one relative to
    # the repo root, because both forms appear in the docs and neither is
    # obviously the "right" one to a user reading a SKIP line. Normalize to
    # absolute up front, and track which entries actually match something —
    # an unmatched --force-materialize used to be ignored in total silence,
    # so a typo (or the wrong path flavor) looked exactly like success.
    force_abs = {str((REPO_ROOT / f).resolve()) for f in force}
    force_used: set[str] = set()
    docker_enabled = cfg.get("DOCKER_ENABLED", "false") == "true"
    accelerators_enabled = cfg.get("ACCELERATORS_ENABLED", "false") == "true"
    latex_enabled = cfg.get("LATEX_DRAFTING_ENABLED", "false") == "true"
    for entry in manifest["materialize"]:
        adapter = adapter_of(entry)
        enabled_adapters = set(cfg.get("ADAPTERS_ENABLED", "claude,antigravity").split(","))
        if adapter and adapter not in enabled_adapters:
            continue
        if entry.get("docker") and not docker_enabled:
            continue
        if entry.get("accelerators") and not accelerators_enabled:
            continue
        if entry.get("latex") and not latex_enabled:
            continue
        src = SUBMODULE_DIR / entry["src"]
        dest = REPO_ROOT / entry["dest"]
        if not src.exists():
            print(f"  WARN: template source missing: {src}")
            continue
        rendered = render(src.read_text(), cfg, drop_sections=sections_to_drop(cfg))
        dest_key = str(dest.resolve()) if dest.exists() else str(dest)
        forced = dest_key in force_abs
        if forced:
            force_used.add(dest_key)
        if dest.exists() and not forced:
            if dest.read_text() != rendered:
                print(f"  SKIP (already materialized, differs from fresh render — use --force-materialize={dest} to overwrite): {dest}")
            continue
        print(f"  {'overwrite' if dest.exists() else 'materialize'} {dest}")
        if not dry_run:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(rendered)
            if src.name in ("pre-commit", "commit-msg") or os.access(src, os.X_OK):
                dest.chmod(dest.stat().st_mode | stat.S_IEXEC)
    for unmatched in sorted(force_abs - force_used):
        print(f"  WARN: --force-materialize={unmatched} matched no materialized file (typo? wrong path? gated off by config?)")


def create_running_dirs(dry_run: bool) -> None:
    """harness/rules/environment.md.tmpl documents background launches
    redirecting output to harness/running/logs/your_script.log. That
    directory isn't a template (git doesn't track empty dirs) so a fresh
    project never gets it — create it with a .gitkeep during sync.
    """
    gitkeep = REPO_ROOT / "harness" / "running" / "logs" / ".gitkeep"
    if gitkeep.exists():
        return
    print(f"  create {gitkeep}")
    if not dry_run:
        gitkeep.parent.mkdir(parents=True, exist_ok=True)
        gitkeep.write_text("")


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


# Every Docker input lives in docker/, including the compose file and the
# Dockerfile — see the header comment in docker/docker-compose.yml.
COMPOSE_PATH = Path("docker/docker-compose.yml")


def ensure_docker_env_symlink(cfg: dict[str, str], dry_run: bool) -> None:
    """Point docker/.env at the repo-root .env.

    Compose resolves `.env` against the project directory, which defaults to
    the compose file's own directory — docker/, not the repo root. Without
    this symlink a root-only .env is silently ignored, so `${USER_UID}` falls
    back to 1000 and bind-mounted files come out owned by the wrong UID on any
    host where the user isn't 1000. The symlink is relative and is fine to
    leave dangling: Compose treats a missing .env as "no overrides", so a
    project that never created one still works.
    """
    if cfg.get("DOCKER_ENABLED", "false") != "true":
        return
    link = REPO_ROOT / "docker" / ".env"
    if link.is_symlink() and os.readlink(link) == "../.env":
        return
    if link.exists() and not link.is_symlink():
        print(f"  REFUSE (real file exists, not overwriting): {link}")
        return
    print(f"  symlink {link} -> ../.env")
    if not dry_run:
        link.parent.mkdir(parents=True, exist_ok=True)
        if link.is_symlink():
            link.unlink()
        link.symlink_to("../.env")


def apply_docker_volumes(cfg: dict[str, str]) -> None:
    compose_path = REPO_ROOT / COMPOSE_PATH
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
    # -f is required now that the compose file lives in docker/. Deliberately
    # NOT paired with --project-directory: the compose file's relative paths
    # are written against docker/ (its own directory, which is the default
    # project directory), and the docker/.env symlink is what keeps the root
    # .env reachable. Overriding the project directory would break both.
    cmd = ["docker", "compose", "-f", str(COMPOSE_PATH), "build"]
    print(f"  running: {' '.join(cmd)}")
    if dry_run:
        return
    try:
        subprocess.run(cmd, cwd=REPO_ROOT, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"  WARN: docker compose build failed: {e}")



# ---------------------------------------------------------------------------
# .gitignore / .gitattributes
# ---------------------------------------------------------------------------


def _active_gitfile_gates(cfg: dict[str, str]) -> set[str]:
    gates = set()
    if cfg.get("LATEX_DRAFTING_ENABLED", "false") == "true":
        gates.add("latex")
    # The reference-PDF ignore rules only matter to projects actually using
    # harness/tools/'s bibliography workflow. There's no dedicated
    # "bibliography enabled" config key, so use the two BIBLIO_* fields the
    # interview always asks for as a proxy: if either was filled in, assume
    # the workflow is in play.
    if cfg.get("BIBLIO_CONTACT_EMAIL", "").strip() or cfg.get("BIBLIO_USER_AGENT_TOKEN", "").strip():
        gates.add("biblio")
    return gates


FRAGMENT_MARKER = "# ---FRAGMENT CONTENT BELOW---\n"


def _render_gitfile_fragment(text: str, active_gates: set[str]) -> list[str]:
    # Drop the maintainer-facing header comment above the marker (if any) —
    # it documents this file for humans editing the fragment, not for a
    # consumer's real .gitignore/.gitattributes.
    if FRAGMENT_MARKER in text:
        text = text.split(FRAGMENT_MARKER, 1)[1]

    def drop_gate(m: re.Match) -> str:
        name = m.group(1)
        return m.group(2) if name in active_gates else ""

    rendered = GATE_RE.sub(drop_gate, text)
    lines = rendered.splitlines()
    cleaned: list[str] = []
    prev_blank = False
    for line in lines:
        if line.strip() == "":
            if prev_blank or not cleaned:
                continue
            cleaned.append("")
            prev_blank = True
        else:
            cleaned.append(line)
            prev_blank = False
    while cleaned and cleaned[-1] == "":
        cleaned.pop()
    return cleaned


def _sync_one_gitfile(fragment_path: Path, dest: Path, cfg: dict[str, str], dry_run: bool) -> None:
    if not fragment_path.exists():
        print(f"  WARN: fragment source missing: {fragment_path}")
        return
    desired = _render_gitfile_fragment(fragment_path.read_text(), _active_gitfile_gates(cfg))
    if not desired:
        return  # nothing gated on for this project (e.g. no LaTeX -> no .gitattributes content)

    existing_text = dest.read_text() if dest.exists() else ""
    outside_text = GIT_MANAGED_BLOCK_RE.sub("", existing_text)
    outside_lines = {
        line.strip()
        for line in outside_text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    }
    # Never duplicate a pattern the consumer file already has outside our
    # managed block. A comment only earns its place if at least one pattern
    # it introduces survives that dedup — otherwise re-syncing a project
    # whose .gitignore already covers everything (the common case when the
    # harness was hand-installed first) appends a block of orphaned comment
    # headers with no patterns under them.
    # Group the fragment into (heading comments, patterns) pairs — a new
    # group starts at the first comment/blank following a pattern — and emit
    # a group only when at least one of its patterns survives dedup.
    groups: list[tuple[list[str], list[str]]] = []
    heading: list[str] = []
    patterns: list[str] = []
    for line in desired:
        stripped = line.strip()
        if stripped.startswith("#") or stripped == "":
            if patterns:
                groups.append((heading, patterns))
                heading, patterns = [], []
            heading.append(line)
        else:
            patterns.append(line)
    if heading or patterns:
        groups.append((heading, patterns))

    block_lines: list[str] = []
    for heading, patterns in groups:
        kept = [p for p in patterns if p.strip() not in outside_lines]
        if not kept:
            continue
        block_lines.extend(heading)
        block_lines.extend(kept)
    while block_lines and block_lines[0].strip() == "":
        block_lines.pop(0)
    if not block_lines:
        return

    new_block = (
        "# --- friday harness (managed by init_harness.py) ---\n"
        + "\n".join(block_lines) + "\n"
        + "# --- end friday harness ---\n"
    )
    if GIT_MANAGED_BLOCK_RE.search(existing_text):
        new_text = GIT_MANAGED_BLOCK_RE.sub(new_block, existing_text)
    else:
        sep = "" if not existing_text or existing_text.endswith("\n") else "\n"
        new_text = existing_text + sep + ("\n" if existing_text else "") + new_block

    if new_text == existing_text:
        return
    print(f"  {'update' if dest.exists() else 'create'} {dest}")
    if not dry_run:
        dest.write_text(new_text)


def sync_git_ignore_attributes(cfg: dict[str, str], dry_run: bool) -> None:
    """Append missing .gitignore / .gitattributes lines idempotently, from
    setup/gitignore.fragment and setup/gitattributes.fragment. Never
    rewrites or reorders content outside our own managed block; content
    inside the managed block is safely regenerated each run (same pattern
    as apply_docker_volumes()'s user-added-volumes block).
    """
    _sync_one_gitfile(SUBMODULE_DIR / "setup" / "gitignore.fragment", REPO_ROOT / ".gitignore", cfg, dry_run)
    _sync_one_gitfile(SUBMODULE_DIR / "setup" / "gitattributes.fragment", REPO_ROOT / ".gitattributes", cfg, dry_run)


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
        if path.is_symlink():
            continue  # shared/generic files (e.g. USER_GUIDE.md) are never a per-project fill-in
        if LEFTOVER_RE.search(path.read_text(errors="ignore")):
            leftovers.append(path)
    for path in (REPO_ROOT / "docs").rglob("*.md"):
        if path.is_symlink():
            continue
        if LEFTOVER_RE.search(path.read_text(errors="ignore")):
            leftovers.append(path)
    for path in (REPO_ROOT / "AGENTS.md", REPO_ROOT / "README.md"):
        if path.exists() and LEFTOVER_RE.search(path.read_text(errors="ignore")):
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
    accel_enabled = cfg.get("ACCELERATORS_ENABLED", "false") == "true"
    gpu_present = (REPO_ROOT / "harness" / "rules" / "gpu.md").exists()
    accel_ok = accel_enabled == gpu_present
    print(f"  [{'x' if accel_ok else ' '}] harness/rules/gpu.md present={gpu_present} matches ACCELERATORS_ENABLED={accel_enabled}")
    latex_enabled = cfg.get("LATEX_DRAFTING_ENABLED", "false") == "true"
    theory_present = (REPO_ROOT / "docs" / "theory" / "README.md").exists()
    latex_ok = latex_enabled == theory_present
    print(f"  [{'x' if latex_ok else ' '}] docs/theory/, docs/report/ present={theory_present} matches LATEX_DRAFTING_ENABLED={latex_enabled}")
    if latex_enabled:
        print("  [ ] LFS is set up for docs/theory/, docs/report/'s generated PDFs — see harness/rules/version_control.md's lfs_policy section")
    print("  [ ] python3 harness/tools/../../.claude/hooks/check_md_hygiene.py (or .agents/hooks/) runs clean — not checked automatically, run it yourself")
    print("  [ ] harness/status.md reflects reality (probably: nothing running yet)")
    print("  [ ] first directive opened from harness/plans/directives/TEMPLATE.md")
    print("  [ ] anything surprising you learned during setup recorded in harness/log.md — that file is the \"why\" behind your rules, and it starts on day one")


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

    print("\n=== harness/running/logs ===")
    create_running_dirs(args.dry_run)

    print("\n=== .gitignore / .gitattributes ===")
    sync_git_ignore_attributes(cfg, args.dry_run)

    if cfg.get("DOCKER_ENABLED") == "true":
        print("\n=== Docker ===")
        # Runs in dry-run too: it only prints there, and it's the one Docker
        # step whose effect a user would want previewed.
        ensure_docker_env_symlink(cfg, args.dry_run)
        if not args.dry_run:
            apply_docker_volumes(cfg)
            maybe_build_docker(cfg, args.dry_run)

    closing_checklist(cfg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
