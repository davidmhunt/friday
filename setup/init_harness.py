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
import ast
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path, PurePosixPath

REPO_ROOT = Path.cwd()
SUBMODULE_DIR = REPO_ROOT / ".friday"
# Most template/source content lives under templates/ inside the submodule
# (VERSION, setup/, MANIFEST.json etc. stay at SUBMODULE_DIR's root) —
# manifest `src` entries resolve against this, not SUBMODULE_DIR directly.
TEMPLATES_DIR = SUBMODULE_DIR / "templates"
# Generated harness output (role/rule docs, status/log/plans state, running
# logs, ...) lives inside the submodule rather than at the consumer repo
# root as of v0.13.0 — dest_root: "active" manifest entries resolve here.
ACTIVE_DIR = SUBMODULE_DIR / "active"
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

# HARNESS_TRACKING controls how much of the harness's footprint gets
# committed to the consumer repo's history at all, as opposed to living only
# on disk and being excluded via .git/info/exclude (see write_git_exclude()).
# Every materialize entry in MANIFEST.json carries a "tier"; every symlinks
# entry is implicitly "tooling" (see MANIFEST.json's _comment). The value
# here is the set of tiers EXCLUDED at that tracking level — "project"
# never appears in any of them, because project-authored content (README,
# AGENTS.md, docs/RESULTS.md, the Docker build inputs, ...) is never
# harness-owned churn and must always be visible to `git status`/`git add`.
TRACKING_TIERS: dict[str, set[str]] = {
    "full": set(),
    "tooling": {"tooling"},
    "state": {"tooling", "state"},
    "none": {"tooling", "state", "durable"},
}
# Default to "tooling", not "state": excluding the derived tooling is pure
# upside (it's regenerable, and tracking it as symlinks into an optional
# submodule breaks any clone made without --recurse-submodules), whereas
# excluding harness STATE trades away cross-machine continuity. status.md and
# plans/ stay tracked by default; a project that wants a cleaner repo can
# still opt into "state" or "none" in the interview.
DEFAULT_HARNESS_TRACKING = "tooling"

# ...unless the project has no task tracker. With one configured, issues are
# an external durable record that survives harness state being local-only.
# Without one, excluding harness state would leave the project with NO record
# of in-flight work that survives a fresh clone, so fall back to tracking
# everything rather than silently dropping the only copy.
NO_TRACKER_HARNESS_TRACKING = "full"

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
            "  in .friday/active/harness/rules/gpu.md (materialized from\n"
            "  templates/harness/rules/gpu.md.tmpl) —\n"
            "  those are free-text [SET AT SETUP: ...] prose blocks the script can't\n"
            "  infer, same as the Project Overview section in AGENTS.md."
        )

    print(
        "\nHow much of the harness's own footprint should this project commit\n"
        "to git, versus leave on disk only (excluded via .git/info/exclude —\n"
        "never .gitignore, so a project that already ignores broadly doesn't\n"
        "collide with it)? Tier \"project\" content (README, AGENTS.md,\n"
        "docs/RESULTS.md, Docker build inputs, ...) is always committed,\n"
        "regardless of this choice:"
    )
    tracking_default = default_tracking_for(cfg)
    print("  1) full     commit everything")
    print(f"  2) tooling  exclude generated tooling (role/rule docs, hooks, adapter configs, symlinks)"
          f"{'  [recommended]' if tracking_default == 'tooling' else ''}")
    print("  3) state    tooling, plus day-to-day harness state (status.md, tasks_*.md, plans/*.md)")
    print("  4) none     tooling + state, plus durable harness history (status_history.md, coding/history.md, plans/history.md)")
    if not _has_task_tracker(cfg):
        # No external durable record, so excluding harness state would leave
        # in-flight work with no copy that survives a fresh clone.
        print("  NOTE: no task tracker configured, so 'full' is recommended here —")
        print("        options 3 and 4 would leave in-flight work on this machine only.")
    tracking_choice = ask(
        "Choice",
        {"full": "1", "tooling": "2", "state": "3", "none": "4"}.get(
            existing.get("HARNESS_TRACKING", ""),
            {"full": "1", "tooling": "2", "state": "3", "none": "4"}[tracking_default],
        ),
    )
    cfg["HARNESS_TRACKING"] = {"1": "full", "2": "tooling", "3": "state", "4": "none"}.get(tracking_choice, tracking_default)
    if cfg["HARNESS_TRACKING"] in ("state", "none") and not _has_task_tracker(cfg):
        print("  WARN: harness state will be excluded from git and this project has no")
        print("        task tracker — in-flight work won't survive a fresh clone.")

    # --- Docker (B.1a) ---
    cfg["DOCKER_ENABLED"] = "true" if ask_yn("\nSet up Docker for this project?", True) else "false"
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
    # docker_node_runtime is split into two mutually exclusive gates, one per
    # Dockerfile stage, so exactly one copy of the Node runtime install ever
    # lands, in the stage that actually needs it:
    #   - docker_node_runtime_dev (the `dev` stage): a Node-based
    #     PACKAGE_MANAGER is a project concern — Node must be present even
    #     for a teammate building `dev` alone, without the harness
    #     submodule.
    #   - docker_node_runtime_harness (the `harness` stage): the Claude Code
    #     CLI is harness tooling layered on top of `dev`. It needs Node too,
    #     but ONLY when `dev` didn't already install it — installing it
    #     twice would waste image layers/build time. So this one is active
    #     exactly when agent_claude is on AND PACKAGE_MANAGER is NOT already
    #     Node-based.
    if not pm_node:
        drop.add("docker_node_runtime_dev")
    if not (agent_claude and not pm_node):
        drop.add("docker_node_runtime_harness")
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


def _has_task_tracker(cfg: dict[str, str]) -> bool:
    # TRACKER_KIND is the interview's own key (none / gitlab-issues /
    # github-issues), set earlier in run_interview() than HARNESS_TRACKING is,
    # so it's always populated by the time this is consulted.
    tracker = cfg.get("TRACKER_KIND", "").strip().lower()
    return bool(tracker) and tracker != "none"


def default_tracking_for(cfg: dict[str, str]) -> str:
    """The HARNESS_TRACKING default appropriate to this project's config."""
    return DEFAULT_HARNESS_TRACKING if _has_task_tracker(cfg) else NO_TRACKER_HARNESS_TRACKING


def resolve_tracking(cfg: dict[str, str]) -> str:
    """Read HARNESS_TRACKING off cfg, falling back to the default.

    A missing key (config written before this feature existed) falls back
    quietly — that's just an old project that hasn't opted in yet, not an
    error. An unrecognized value (hand-edited config, typo) is a real
    mistake worth flagging, so that one gets a WARN naming the bad value
    before falling back the same way.

    An EXPLICIT choice is always honoured, including one that excludes
    harness state on a project with no task tracker: the interview warns
    about that combination at the point of choosing (see run_interview()),
    and silently overriding what the config file plainly says would be
    worse than letting the user own the tradeoff.
    """
    fallback = default_tracking_for(cfg)
    raw = cfg.get("HARNESS_TRACKING", "")
    if not raw:
        return fallback
    if raw not in TRACKING_TIERS:
        print(f"  WARN: unrecognized HARNESS_TRACKING={raw!r}, falling back to {fallback!r}")
        return fallback
    return raw


def resolve_manifest_src(entry: dict) -> Path:
    """Resolve a manifest entry's `src` string to a file inside the submodule.

    Dispatches explicitly on the entry's `src_root` (default "templates")
    rather than trying templates/ and silently falling back to the
    submodule root: a typo'd src would otherwise resolve at the wrong root
    with no error, since Path.exists() would happily report the fallback
    location as present. "submodule" is reserved for the handful of entries
    (USER_GUIDE.md) that deliberately live at the submodule root rather than
    under templates/.
    """
    src_root = entry.get("src_root", "templates")
    if src_root == "submodule":
        return SUBMODULE_DIR / entry["src"]
    if src_root == "templates":
        return TEMPLATES_DIR / entry["src"]
    raise ValueError(f"unrecognized src_root {src_root!r} on manifest entry {entry!r}")


def dest_base(entry: dict) -> Path:
    """The base directory a manifest entry's `dest` resolves against.

    "repo" (default when absent) is the consumer repo root; "active" is
    .friday/active/ — used for every generated harness/... path now that the
    harness's generated output lives inside the submodule instead of at the
    consumer root (v0.13.0).
    """
    dest_root = entry.get("dest_root", "repo")
    if dest_root == "active":
        return ACTIVE_DIR
    if dest_root == "repo":
        return REPO_ROOT
    raise ValueError(f"unrecognized dest_root {dest_root!r} on manifest entry {entry!r}")


def sync_symlinks(manifest: dict, cfg: dict[str, str], dry_run: bool) -> None:
    enabled_adapters = set(cfg.get("ADAPTERS_ENABLED", "claude,antigravity").split(","))
    docker_enabled = cfg.get("DOCKER_ENABLED", "false") == "true"
    for entry in manifest["symlinks"]:
        adapter = adapter_of(entry)
        if adapter and adapter not in enabled_adapters:
            continue
        if entry.get("docker") and not docker_enabled:
            continue
        src = resolve_manifest_src(entry).resolve()
        dest = dest_base(entry) / entry["dest"]
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


def compute_excluded_paths(manifest: dict, cfg: dict[str, str], tracking: str | None = None) -> list[str]:
    """The consumer-repo-relative dest paths that HARNESS_TRACKING says
    should never touch git history, given this project's actual config.

    Mirrors the same adapter/docker/accelerators/latex gating sync_symlinks()
    and materialize_files() apply — a file that config gates off is never
    created in the first place, so it must never show up in an exclude list
    either (an exclude pattern for a nonexistent path is at best noise, and
    at worst masks the fact that the file is missing when it should exist).

    Only considers `dest_root: "repo"` entries (the default, when absent):
    an "active"-rooted dest lives inside .friday/active/, which is not a
    consumer-repo path at all (it's excluded wholesale by the submodule's
    own .gitignore) — emitting it into .git/info/exclude here would produce
    an entry relative to the consumer repo root that can never match
    anything.

    `tracking` lets a caller that already resolved HARNESS_TRACKING (and
    already printed its WARN, if the value was bad) pass that result straight
    through instead of triggering a second, duplicate WARN here.
    """
    excluded_tiers = TRACKING_TIERS[tracking if tracking is not None else resolve_tracking(cfg)]
    enabled_adapters = set(cfg.get("ADAPTERS_ENABLED", "claude,antigravity").split(","))
    docker_enabled = cfg.get("DOCKER_ENABLED", "false") == "true"
    accelerators_enabled = cfg.get("ACCELERATORS_ENABLED", "false") == "true"
    latex_enabled = cfg.get("LATEX_DRAFTING_ENABLED", "false") == "true"

    paths: list[str] = []
    if "tooling" in excluded_tiers:
        # Every symlinks entry is implicitly tier "tooling" — see
        # MANIFEST.json's _comment.
        for entry in manifest["symlinks"]:
            if entry.get("dest_root", "repo") != "repo":
                continue
            adapter = adapter_of(entry)
            if adapter and adapter not in enabled_adapters:
                continue
            if entry.get("docker") and not docker_enabled:
                continue
            paths.append(entry["dest"])
    for entry in manifest["materialize"]:
        if entry.get("dest_root", "repo") != "repo":
            continue
        if entry.get("tier") not in excluded_tiers:
            continue
        adapter = adapter_of(entry)
        if adapter and adapter not in enabled_adapters:
            continue
        if entry.get("docker") and not docker_enabled:
            continue
        if entry.get("accelerators") and not accelerators_enabled:
            continue
        if entry.get("latex") and not latex_enabled:
            continue
        paths.append(entry["dest"])
    return sorted(set(paths))


def materialize_files(manifest: dict, cfg: dict[str, str], dry_run: bool, force: set[str]) -> None:
    # --force-materialize accepts either an absolute path or one relative to
    # the repo root, because both forms appear in the docs and neither is
    # obviously the "right" one to a user reading a SKIP line. Normalize to
    # absolute up front, and track which entries actually match something —
    # an unmatched --force-materialize used to be ignored in total silence,
    # so a typo (or the wrong path flavor) looked exactly like success.
    # Active-rooted dests (dest_root: "active") live under .friday/active/,
    # not the repo root, so a relative --force-materialize is normalized
    # against BOTH bases — an absolute path or a path that happens to
    # collide under both is unaffected, since Path.__truediv__ with an
    # absolute second operand just returns that operand unchanged.
    force_abs = {str((REPO_ROOT / f).resolve()) for f in force}
    force_abs |= {str((ACTIVE_DIR / f).resolve()) for f in force}
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
        src = resolve_manifest_src(entry)
        dest = dest_base(entry) / entry["dest"]
        if not src.exists():
            print(f"  WARN: template source missing: {src}")
            continue
        rendered = render(src.read_text(), cfg, drop_sections=sections_to_drop(cfg))
        dest_key = str(dest.resolve()) if dest.exists() else str(dest)
        forced = dest_key in force_abs
        if forced:
            force_used.add(dest_key)
        if dest.exists() and not forced:
            # seed_once entries (currently just README.md) are a one-time
            # scaffold, not harness-owned churn: the project starts editing
            # it the moment setup finishes, so "differs from fresh render"
            # is the EXPECTED steady state, not a drift signal worth a SKIP
            # line every re-run. Silence is the point here.
            if not entry.get("seed_once") and dest.read_text() != rendered:
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
    """templates/harness/rules/environment.md.tmpl documents background
    launches redirecting output to
    .friday/active/harness/running/logs/your_script.log. That
    directory isn't a template (git doesn't track empty dirs) so a fresh
    project never gets it — create it with a .gitkeep during sync.
    """
    gitkeep = ACTIVE_DIR / "harness" / "running" / "logs" / ".gitkeep"
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


# Every Docker input lives in docker/, including the compose files and the
# Dockerfile — see the header comment in docker/docker-compose.yml.
COMPOSE_PATH = Path("docker/docker-compose.yml")
# The harness override — see docker/docker-compose.harness.yml.tmpl's header.
# Stacked onto COMPOSE_PATH with -f so setup always builds/runs the full
# `harness` image, which is what a submodule-having project actually wants
# (a project-only `dev` build never runs this script in the first place).
COMPOSE_HARNESS_PATH = Path("docker/docker-compose.harness.yml")


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


COMPOSE_FILE_LINE_RE = re.compile(r"^COMPOSE_FILE=.*$", re.MULTILINE)
COMPOSE_FILE_VALUE = "docker/docker-compose.yml:docker/docker-compose.harness.yml"


def ensure_compose_file_env(cfg: dict[str, str], dry_run: bool) -> None:
    """Write `COMPOSE_FILE=docker/docker-compose.yml:docker/docker-compose.harness.yml`
    into the repo-root .env, creating it if missing.

    This is what makes a plain `docker compose up -d` (no -f flags) stack the
    harness override on top of the base file automatically for anyone who
    ran this setup script with the .friday/ submodule present. A teammate
    with no .env at all (never ran setup, or has no submodule) gets ONLY the
    base file and its agent-CLI-free `dev` image — see
    docker/docker-compose.yml's header comment.

    Idempotent and non-destructive: an existing COMPOSE_FILE= line is
    updated in place, and every other line in .env is left untouched — this
    function must never clobber secrets or other settings a project has
    already put there.
    """
    if cfg.get("DOCKER_ENABLED", "false") != "true":
        return
    env_path = REPO_ROOT / ".env"
    existing_text = env_path.read_text() if env_path.exists() else ""
    new_line = f"COMPOSE_FILE={COMPOSE_FILE_VALUE}"
    if COMPOSE_FILE_LINE_RE.search(existing_text):
        if COMPOSE_FILE_LINE_RE.search(existing_text).group(0) == new_line:
            return
        new_text = COMPOSE_FILE_LINE_RE.sub(new_line, existing_text, count=1)
    else:
        sep = "" if not existing_text or existing_text.endswith("\n") else "\n"
        new_text = existing_text + sep + new_line + "\n"
    print(f"  {'update' if env_path.exists() else 'create'} {env_path} (COMPOSE_FILE=...)")
    if dry_run:
        return
    env_path.write_text(new_text)


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
    # -f is required now that the compose files live in docker/. Deliberately
    # NOT paired with --project-directory: the compose files' relative paths
    # are written against docker/ (its own directory, which is the default
    # project directory), and the docker/.env symlink is what keeps the root
    # .env reachable. Overriding the project directory would break both.
    #
    # Both -f flags are passed explicitly (rather than relying on the
    # COMPOSE_FILE=... line ensure_compose_file_env() just wrote to .env) so
    # this always builds the `harness` stage regardless of whether that env
    # var has been picked up by the current shell/subprocess environment —
    # this is the one Docker step a project that ran this setup script
    # actually wants: the full agent-tooling image, not just `dev`.
    cmd = [
        "docker", "compose",
        "-f", str(COMPOSE_PATH),
        "-f", str(COMPOSE_HARNESS_PATH),
        "build",
    ]
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
    # .friday/active/harness/tools/'s bibliography workflow. There's no dedicated
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


def _upsert_managed_block(existing_text: str, block_lines: list[str]) -> str:
    """Insert or replace the "# --- friday harness (managed by
    init_harness.py) ---" block inside existing_text with one built from
    block_lines. Assumes block_lines is non-empty — a caller with nothing to
    write decides for itself what that should mean (see write_git_exclude()
    vs. _sync_one_gitfile(), which disagree: one strips a now-empty block,
    the other leaves a stale one alone).
    """
    new_block = (
        "# --- friday harness (managed by init_harness.py) ---\n"
        + "\n".join(block_lines) + "\n"
        + "# --- end friday harness ---\n"
    )
    if GIT_MANAGED_BLOCK_RE.search(existing_text):
        return GIT_MANAGED_BLOCK_RE.sub(new_block, existing_text)
    sep = "" if not existing_text or existing_text.endswith("\n") else "\n"
    return existing_text + sep + ("\n" if existing_text else "") + new_block


def _drop_shadowed_negations(lines: list[str], excluded: set[str]) -> list[str]:
    """Remove `!path` re-include lines for paths the harness now excludes.

    .gitignore takes precedence over .git/info/exclude — for the SAME path, a
    negation in .gitignore wins outright. So a fragment line like
    `!docs/references/inbox/README.md`, which exists to keep the
    directory's own README tracked, silently defeats the exclude entry for
    that same file and leaks it back into `git status` at any
    HARNESS_TRACKING below `full`.

    Dropping the negation here rather than gating it in the fragment keeps
    this correct automatically as tiers change, and avoids nesting a GATE
    inside the existing `biblio` gate — GATE_RE.sub() is single-pass, so a
    nested gate's markers would survive into the rendered output verbatim.
    """
    if not excluded:
        return lines
    kept: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("!") and stripped[1:].strip().lstrip("/") in excluded:
            continue
        kept.append(line)
    return kept


def _warn_shadowing_negations(dest: Path, excluded: set[str]) -> None:
    """Flag `!path` lines OUTSIDE our managed block that defeat the exclude.

    _drop_shadowed_negations() can only filter lines this script is about to
    render into its own managed block. A project that hand-installed the
    harness, or that ran a version predating the managed block, has those
    negations sitting in .gitignore as ordinary user content — and
    _sync_one_gitfile() deliberately never rewrites anything outside the
    block, since that content may be the user's own.

    So warn rather than edit: silently deleting a line someone wrote by hand
    is worse than telling them it's there. Without this the failure is
    invisible — the file simply keeps showing up in `git status` with no
    indication why .git/info/exclude isn't taking effect.
    """
    if not excluded or not dest.exists():
        return
    outside_text = GIT_MANAGED_BLOCK_RE.sub("", dest.read_text())
    for lineno, line in enumerate(outside_text.splitlines(), 1):
        stripped = line.strip()
        if not stripped.startswith("!"):
            continue
        if stripped[1:].strip().lstrip("/") in excluded:
            print(f"  WARN: {dest.name}:{lineno} '{stripped}' re-includes a path the harness excludes.")
            print(f"        .gitignore beats .git/info/exclude, so that file stays visible to git.")
            print(f"        Remove the line by hand if you want it excluded.")


def _sync_one_gitfile(
    fragment_path: Path,
    dest: Path,
    cfg: dict[str, str],
    dry_run: bool,
    excluded: set[str] | None = None,
) -> None:
    if not fragment_path.exists():
        print(f"  WARN: fragment source missing: {fragment_path}")
        return
    desired = _render_gitfile_fragment(fragment_path.read_text(), _active_gitfile_gates(cfg))
    desired = _drop_shadowed_negations(desired, excluded or set())
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

    new_text = _upsert_managed_block(existing_text, block_lines)
    if new_text == existing_text:
        return
    print(f"  {'update' if dest.exists() else 'create'} {dest}")
    if not dry_run:
        dest.write_text(new_text)


def sync_git_ignore_attributes(
    cfg: dict[str, str], dry_run: bool, excluded: set[str] | None = None
) -> None:
    """Append missing .gitignore / .gitattributes lines idempotently, from
    setup/gitignore.fragment and setup/gitattributes.fragment. Never
    rewrites or reorders content outside our own managed block; content
    inside the managed block is safely regenerated each run (same pattern
    as apply_docker_volumes()'s user-added-volumes block).

    `excluded` is the .git/info/exclude path set; any `!path` negation for a
    path in it is dropped, since .gitignore would otherwise override the
    exclude and leak the file back (see _drop_shadowed_negations()).
    """
    _sync_one_gitfile(
        SUBMODULE_DIR / "setup" / "gitignore.fragment", REPO_ROOT / ".gitignore", cfg, dry_run, excluded
    )
    _warn_shadowing_negations(REPO_ROOT / ".gitignore", excluded or set())
    # .gitattributes carries no negations, so the exclude set is irrelevant there.
    _sync_one_gitfile(SUBMODULE_DIR / "setup" / "gitattributes.fragment", REPO_ROOT / ".gitattributes", cfg, dry_run)


# ---------------------------------------------------------------------------
# HARNESS_TRACKING: .git/info/exclude + --untrack-harness
# ---------------------------------------------------------------------------


def _git_info_exclude_path() -> Path:
    # `.git` is a FILE (not a directory) inside a submodule or a worktree —
    # it contains a `gitdir: <real path>` pointer instead. Only `git
    # rev-parse --git-dir` resolves that correctly in every case; assuming
    # REPO_ROOT/".git"/"info"/"exclude" breaks for exactly the repos this
    # feature exists for (a consumer project with .friday/ as a submodule is
    # itself frequently a submodule of something else, or checked out as a
    # worktree).
    result = subprocess.run(
        ["git", "rev-parse", "--git-dir"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=True,
    )
    git_dir = Path(result.stdout.strip())
    if not git_dir.is_absolute():
        git_dir = (REPO_ROOT / git_dir).resolve()
    return git_dir / "info" / "exclude"


def write_git_exclude(manifest: dict, cfg: dict[str, str], dry_run: bool) -> None:
    """Exclude harness-generated files via .git/info/exclude, never
    .gitignore. .git/info/exclude is local-only and untracked by design — it
    never becomes part of the consumer repo's history, so it can't collide
    with a project's own .gitignore conventions or leak our opinions about
    what counts as "harness noise" into a commit. This is what makes
    HARNESS_TRACKING < full possible without asking the project to adopt any
    new convention of its own.
    """
    tracking = resolve_tracking(cfg)
    excluded = compute_excluded_paths(manifest, cfg, tracking=tracking)
    exclude_path = _git_info_exclude_path()
    existing_text = exclude_path.read_text() if exclude_path.exists() else ""
    block_lines = [f"/{p}" for p in excluded]

    if block_lines:
        new_text = _upsert_managed_block(existing_text, block_lines)
    else:
        # HARNESS_TRACKING=full excludes no tier. Unlike
        # _sync_one_gitfile()'s "leave a stale block alone" rule, a shrinking
        # exclude set here must actually shrink — otherwise switching a
        # project from e.g. "state" back to "full" would silently leave
        # yesterday's exclusions in effect and the promised file would still
        # never show up in `git status`.
        new_text = GIT_MANAGED_BLOCK_RE.sub("", existing_text)

    if new_text == existing_text:
        print(f"  {len(excluded)} path(s) excluded at HARNESS_TRACKING={tracking} (no change to {exclude_path})")
        return
    verb = "would update" if dry_run else ("update" if exclude_path.exists() else "create")
    print(f"  {verb} {exclude_path}")
    if dry_run:
        print(f"  {len(excluded)} path(s) would be excluded at HARNESS_TRACKING={tracking}")
        return
    exclude_path.parent.mkdir(parents=True, exist_ok=True)
    exclude_path.write_text(new_text)
    print(f"  {len(excluded)} path(s) excluded at HARNESS_TRACKING={tracking}")


def _untrack_paths(candidates: set[str], dry_run: bool, nothing_msg: str, found_label: str) -> None:
    """Shared body of --untrack-harness and --untrack-legacy: `git rm
    --cached` the intersection of `candidates` with `git ls-files`.

    Intersecting with an explicit, caller-supplied path set (never a glob,
    never a directory, never `-r`) is the safety property that makes both
    commands trustworthy to run unattended — this helper is structurally
    incapable of touching a file that isn't already in `candidates`, no
    matter what else `git ls-files` happens to report. It never commits;
    it only stages the removal for the operator to review and commit
    themselves.
    """
    result = subprocess.run(
        ["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True, check=True,
    )
    tracked = set(result.stdout.splitlines())
    to_untrack = sorted(candidates & tracked)
    if not to_untrack:
        print(f"  {nothing_msg}")
        return

    print(f"  {len(to_untrack)} tracked file(s) {found_label}:")
    for path in to_untrack:
        print(f"    {path}")
    if dry_run:
        return
    # Explicit file list, never -r on a directory: every candidate here is a
    # single file (a manifest dest or a legacy_dests entry), and passing
    # directories would risk sweeping in something neither list names.
    subprocess.run(["git", "rm", "--cached", "--"] + to_untrack, cwd=REPO_ROOT, check=True)
    print(f"  Ran `git rm --cached` on {len(to_untrack)} file(s). Nothing committed —")
    print("  review `git status` and commit the removal yourself when ready.")


def untrack_harness(manifest: dict, cfg: dict[str, str], dry_run: bool) -> None:
    """`git rm --cached` every currently-tracked file that HARNESS_TRACKING
    says should be excluded going forward.

    This exists for the project that adopted HARNESS_TRACKING (or lowered
    it) after already committing some of the harness's generated files —
    write_git_exclude() only stops NEW commits from picking them up, it
    can't retroactively drop what's already tracked. Intersecting with the
    manifest-derived exclude set (never a glob, never a directory) is the
    safety property that makes this command trustworthy to run unattended:
    it is structurally incapable of touching a file the manifest doesn't
    know about, tier "project" included.
    """
    tracking = resolve_tracking(cfg)
    excluded = set(compute_excluded_paths(manifest, cfg, tracking=tracking))
    if not excluded:
        print(f"  Nothing to untrack — HARNESS_TRACKING={tracking} excludes no tier.")
        return
    _untrack_paths(
        excluded, dry_run,
        "Nothing to untrack — no excluded path is currently tracked by git.",
        "fall under the current exclude set",
    )


def untrack_legacy(manifest: dict, dry_run: bool) -> None:
    """`git rm --cached` every currently-tracked file listed in
    MANIFEST.json's `legacy_dests` — the harness/** dests that existed
    before v0.13.0 relocated the whole harness/ tree into
    .friday/active/harness/.

    This is --untrack-harness's counterpart for that move, not a
    replacement for it: once v0.13.0 lands, no entry in `symlinks` or
    `materialize` has a `harness/…` dest any more, so
    compute_excluded_paths() (and therefore untrack_harness()) can never
    again produce one of those paths — the intersection with `git
    ls-files` that untrack_harness() relies on goes structurally empty for
    exactly the files this command exists to remove. A project that
    committed harness/** before upgrading past `legacy_dests.since` still
    needs a way to drop those now-stale paths from git so the post-move
    symlink tree (materializing under .friday/active/harness/ instead)
    doesn't collide with them. legacy_dests.paths is a frozen snapshot
    for exactly that purpose — it must never be "kept in sync" with the
    current manifest, since its entire job is to remember dests the
    current manifest has already forgotten.
    """
    legacy = manifest.get("legacy_dests", {}).get("paths", [])
    if not legacy:
        print("  Nothing to untrack — no legacy_dests in MANIFEST.json.")
        return
    _untrack_paths(
        set(legacy), dry_run,
        "Nothing to untrack — no legacy_dests path is currently tracked by git.",
        "are pre-v0.13.0 harness/** paths that have moved into .friday/active/",
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


# Directories the harness always populates by means OTHER than a
# MANIFEST.json `dest` (a dynamically-created dir like
# .friday/active/harness/running/logs/
# — see create_running_dirs() — or a directory whose own README.md IS a
# manifest dest, which already makes the directory itself manifest-derived,
# but is listed here too for readability at the call site below). A
# hardcoded path table is allowed to reference anything under one of these
# without that reference being manifest-checkable, because the harness
# itself, not a project's hand-authored content, is what guarantees the
# directory exists.
ALWAYS_GENERATED_DIRS = {
    ".friday/active/harness/running",
    ".friday/active/harness/running/logs",
    ".friday/active/harness/plans/directives",
    "docs/references",
}


def _parse_module_constant(path: Path, name: str):
    """Read a top-level `NAME = <literal>` assignment out of `path` by
    parsing its AST — never by importing it.

    check_md_hygiene.py runs `REPO_ROOT = find_repo_root()` at import time
    (an upward filesystem search, see that module's docstring), and
    check_unavailable_sources.py has import-time side effects of its own
    (it inserts a path and imports sibling tools). Importing either module
    from here — a script that itself may be running from a submodule
    checkout with no consumer project around it yet — would trigger those
    searches/imports against the wrong tree, or fail outright. `ast.parse` +
    `ast.literal_eval` reads the literal value straight off the source text,
    with no side effects and no dependency on the current working directory.
    """
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return ast.literal_eval(node.value)
    raise ValueError(f"{name!r} not found as a top-level assignment in {path}")


def _consumer_relative_dest(entry: dict) -> str:
    """The consumer-repo-root-relative path a manifest entry's `dest`
    actually lands at, accounting for `dest_root`. An "active"-rooted dest
    lives inside the submodule at .friday/active/, not at the dest string
    itself — a hardcoded path table that names such a path (e.g.
    check_md_hygiene.py's FILE_CAPS) must use THIS form, not the bare
    manifest `dest`.
    """
    if entry.get("dest_root", "repo") == "active":
        return f".friday/active/{entry['dest']}"
    return entry["dest"]


def _manifest_dest_dirs(manifest: dict) -> tuple[set[str], set[str]]:
    """(dest paths, directories containing a dest path, all ancestor levels
    included) across both `symlinks` and `materialize`, expressed as
    consumer-repo-root-relative paths (see _consumer_relative_dest())."""
    dests = {_consumer_relative_dest(entry) for entry in manifest["symlinks"] + manifest["materialize"]}
    dirs: set[str] = set()
    for dest in dests:
        parts = PurePosixPath(dest).parts[:-1]
        for i in range(1, len(parts) + 1):
            dirs.add("/".join(parts[:i]))
    return dests, dirs


def check_hardcoded_path_tables(manifest: dict) -> None:
    """Fail loudly if templates/adapters/hooks/check_md_hygiene.py's FILE_CAPS /
    PER_ENTRY_FILE, or templates/harness/tools/check_unavailable_sources.py's
    SCAN_GLOBS, name a path MANIFEST.json no longer knows about.

    Both modules carry their own hardcoded copy of a subset of the path
    layout — check_md_hygiene.py because it's deliberately dependency-free
    (see its module docstring), check_unavailable_sources.py because a glob
    root isn't the kind of thing that belongs in MANIFEST.json's flat
    src/dest entries. Neither copy is derived from the manifest, so nothing
    stops them drifting out of sync with it — and the failure mode when they
    do is silent: a file the manifest moved or renamed simply stops being
    hygiene-checked or scanned, with no error, no warning, just a hole in
    coverage nobody notices until much later. This check exists so that
    drift is a loud preflight failure instead. It's the reason this whole
    exercise (items 2-4 of the v0.13.0 prep work) matters: the upcoming
    harness/** relocation into .friday/active/harness/ is exactly the kind
    of manifest-wide dest change that would otherwise silently break both
    tables the moment it lands.
    """
    dests, manifest_dirs = _manifest_dest_dirs(manifest)
    allowed_dirs = manifest_dirs | ALWAYS_GENERATED_DIRS

    def _covered(path: str) -> bool:
        if path in dests:
            return True
        parent = str(PurePosixPath(path).parent)
        return parent in allowed_dirs

    errors: list[str] = []

    hygiene_path = TEMPLATES_DIR / "adapters" / "hooks" / "check_md_hygiene.py"
    file_caps = _parse_module_constant(hygiene_path, "FILE_CAPS")
    for path in file_caps:
        if not _covered(path):
            errors.append(f"check_md_hygiene.py FILE_CAPS[{path!r}] is not a manifest dest or a harness-generated path")
    per_entry_file = _parse_module_constant(hygiene_path, "PER_ENTRY_FILE")
    if not _covered(per_entry_file):
        errors.append(f"check_md_hygiene.py PER_ENTRY_FILE={per_entry_file!r} is not a manifest dest or a harness-generated path")

    scan_path = TEMPLATES_DIR / "harness" / "tools" / "check_unavailable_sources.py"
    scan_globs = _parse_module_constant(scan_path, "SCAN_GLOBS")
    for scan_dir, _pattern in scan_globs:
        if scan_dir not in allowed_dirs:
            errors.append(f"check_unavailable_sources.py SCAN_GLOBS entry {scan_dir!r} is not a manifest dest directory or a harness-generated directory")

    if errors:
        print("Hardcoded path table(s) have drifted from MANIFEST.json:")
        for e in errors:
            print(f"  {e}")
        print("Update the offending constant(s), or MANIFEST.json, so they agree again.")
        sys.exit(1)


def preflight() -> dict:
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
    manifest = json.loads(MANIFEST_PATH.read_text())
    check_hardcoded_path_tables(manifest)
    return manifest


def closing_checklist(cfg: dict[str, str]) -> None:
    print("\n=== Closing checklist ===")
    leftovers = []
    for path in (ACTIVE_DIR / "harness").rglob("*.md"):
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
    gpu_present = (ACTIVE_DIR / "harness" / "rules" / "gpu.md").exists()
    accel_ok = accel_enabled == gpu_present
    print(f"  [{'x' if accel_ok else ' '}] .friday/active/harness/rules/gpu.md present={gpu_present} matches ACCELERATORS_ENABLED={accel_enabled}")
    latex_enabled = cfg.get("LATEX_DRAFTING_ENABLED", "false") == "true"
    theory_present = (REPO_ROOT / "docs" / "theory" / "README.md").exists()
    latex_ok = latex_enabled == theory_present
    print(f"  [{'x' if latex_ok else ' '}] docs/theory/, docs/report/ present={theory_present} matches LATEX_DRAFTING_ENABLED={latex_enabled}")
    if latex_enabled:
        print("  [ ] LFS is set up for docs/theory/, docs/report/'s generated PDFs — see .friday/active/harness/rules/version_control.md's lfs_policy section")
    print("  [ ] python3 .claude/hooks/check_md_hygiene.py (or .agents/hooks/) runs clean — not checked automatically, run it yourself")
    print("  [ ] .friday/active/harness/status.md reflects reality (probably: nothing running yet)")
    print("  [ ] first directive opened from .friday/active/harness/plans/directives/TEMPLATE.md")
    print("  [ ] anything surprising you learned during setup recorded in .friday/active/harness/log.md — that file is the \"why\" behind your rules, and it starts on day one")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reconfigure", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force-materialize", action="append", default=[])
    parser.add_argument(
        "--untrack-harness", action="store_true",
        help="git rm --cached every already-tracked file that HARNESS_TRACKING now says to exclude, then exit. Never commits.",
    )
    parser.add_argument(
        "--untrack-legacy", action="store_true",
        help="git rm --cached every already-tracked file listed in MANIFEST.json's legacy_dests (pre-v0.13.0 harness/** dests that moved to .friday/active/harness/), then exit. Never commits.",
    )
    args = parser.parse_args()

    manifest = preflight()
    existing = load_config()

    if args.untrack_legacy:
        # No harness.config.env / HARNESS_TRACKING dependency, unlike
        # --untrack-harness: legacy_dests is a fixed list straight off the
        # manifest, not something derived from this project's interview
        # answers, so there is nothing here that requires setup to have run
        # first.
        print("\n=== --untrack-legacy ===")
        untrack_legacy(manifest, args.dry_run)
        return 0

    if args.untrack_harness:
        if not existing:
            print("No harness.config.env found — run the setup interview first (plain `python3 .friday/setup/init_harness.py`).")
            return 1
        print("\n=== --untrack-harness ===")
        untrack_harness(manifest, existing, args.dry_run)
        return 0

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

    print("\n=== .friday/active/harness/running/logs ===")
    create_running_dirs(args.dry_run)

    # Computed before the .gitignore sync, not after: a `!path` negation in
    # the fragment would otherwise override the exclude entry for that same
    # path and leak it back into `git status`.
    excluded_paths = set(compute_excluded_paths(manifest, cfg))

    print("\n=== .gitignore / .gitattributes ===")
    sync_git_ignore_attributes(cfg, args.dry_run, excluded_paths)

    print("\n=== .git/info/exclude (HARNESS_TRACKING) ===")
    write_git_exclude(manifest, cfg, args.dry_run)

    if cfg.get("DOCKER_ENABLED") == "true":
        print("\n=== Docker ===")
        # Runs in dry-run too: it only prints there, and it's the one Docker
        # step whose effect a user would want previewed.
        ensure_docker_env_symlink(cfg, args.dry_run)
        ensure_compose_file_env(cfg, args.dry_run)
        if not args.dry_run:
            apply_docker_volumes(cfg)
            maybe_build_docker(cfg, args.dry_run)

    closing_checklist(cfg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
