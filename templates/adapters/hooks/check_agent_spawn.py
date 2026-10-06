#!/usr/bin/env python3
"""PreToolUse hook on the subagent-spawn tool — `invoke_subagent` under
Antigravity, `Agent`/`Task` under Claude Code (one implementation, shared by
both adapters; the title is the `Role`/`description` field).

Mechanically enforces the spawn-title convention (.friday/active/harness/harness.md §Dispatch,
.friday/active/harness/rules/conventions.md §Spawn titles).

Hard-blocks a role spawn whose title / Role isn't `role(model): task`, and
soft-warns when a `[heavy]`-tagged spawn is invoked without high-tier escalation
(e.g. invoking base `coder` instead of `coder-heavy` on Antigravity, or a
Claude spawn without an explicit high-tier `model`).
Advisory checks never block; the format check does.

Contract (Antigravity PreToolUse hook, per agy-customizations hooks spec):
  - stdin: one JSON object with `toolCall: {name, args}` plus common fields
    (`conversationId`, `modelName`, `workspacePaths`, etc).
  - stdout: JSON with top-level `decision` in {"allow","deny","ask","force_ask"}
    and optional human-readable `reason`.
  - Exit 0 always — the decision lives in the payload; malformed input fails
    OPEN (allow), so a hook bug can never wedge a session.

Dependency-free, can be exercised standalone:
    echo '{"toolCall":{"name":"invoke_subagent","args":{"Subagents":[{"TypeName":"coder","Role":"bad title"}]}}}' \
      | python3 check_agent_spawn.py
"""

import json
import re
import sys
from pathlib import Path

# The base harness roles and their variant mappings.
# Any subagent type not in this set is a utility spawn and exempt.
HARNESS_ROLES = {"controller", "planner", "coder", "runner", "reviewer", "author", "researcher", "editor", "architect"}

# Map each variant name back to its base harness role
VARIANT_TO_BASE = {
    "planner-heavy": "planner",
    "coder-heavy": "coder",
    "runner-judgment": "runner",
    "reviewer-heavy": "reviewer",
    "researcher-heavy": "researcher",
    "researcher-quick": "researcher",
    "editor-heavy": "editor",
    "architect-heavy": "architect",
}

# Map base roles to their high-tier [heavy] escalation variant
HEAVY_VARIANTS = {
    "planner": "planner-heavy",
    "coder": "coder-heavy",
    "reviewer": "reviewer-heavy",
    "researcher": "researcher-heavy",
    "editor": "editor-heavy",
    "architect": "architect-heavy",
}

ALL_HARNESS_ROLE_TYPES = HARNESS_ROLES | set(VARIANT_TO_BASE.keys())

TIER_TABLE = (
    "Controller=mid (inherit) | Planner=mid (inherit) ([heavy] task -> planner-heavy/pro) | "
    "Coder=mid (inherit) ([heavy] task -> coder-heavy/pro) | "
    "Runner=light (flash) (judgment -> runner-judgment/inherit) | "
    "Reviewer=mid (inherit) ([heavy] task -> reviewer-heavy/pro) | Author=mid (inherit) | "
    "Researcher=mid (inherit) ([heavy]/proof-bearing task -> researcher-heavy/pro; "
    "quick lookup -> researcher-quick/inherit) | "
    "Editor=mid (inherit) ([heavy] doc -> editor-heavy/pro) | "
    "Architect=mid (inherit) (phase-level spec -> architect-heavy/pro)"
)

# Project-specific specialist roles (v0.18.0): a project registers an extra
# role by tracking `.friday-project/roles/<role>.md` in its own repo — file
# presence IS the registration, there is no config key to keep in sync.
# Each one is treated like a mid-tier core role with a `<role>-heavy`
# escalation variant (Antigravity) / high-tier model override (Claude).
# A name that collides with a core role or variant is ignored: projects add
# roles, they never redefine core ones.
PROJECT_ROLES_DIR = Path(".friday-project") / "roles"
_ROLE_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def _find_consumer_root() -> Path | None:
    """Consumer repo root by upward search from cwd, then from this file's
    UNRESOLVED directory (it is reached through a symlink; see
    check_md_hygiene.py's docstring for why `.resolve()` is wrong here)."""
    for start in (Path.cwd(), Path(__file__).parent):
        for candidate in (start, *start.parents):
            if (candidate / "harness.config.env").exists() or (
                (candidate / ".gitmodules").exists() and (candidate / ".friday").is_dir()
            ):
                return candidate
    return None


def discover_project_roles(root: Path | None) -> list[str]:
    """Sorted project-role names found under `root/.friday-project/roles/`."""
    if root is None:
        return []
    roles_dir = root / PROJECT_ROLES_DIR
    if not roles_dir.is_dir():
        return []
    names = []
    for path in sorted(roles_dir.glob("*.md")):
        name = path.stem.lower()
        if name == "readme" or not _ROLE_NAME_RE.match(name):
            continue
        if name in HARNESS_ROLES or name in VARIANT_TO_BASE:
            continue
        names.append(name)
    return names


def register_project_roles(names: list[str]) -> None:
    """Add project roles to the role tables (idempotent)."""
    global ALL_HARNESS_ROLE_TYPES, TIER_TABLE
    for name in names:
        if name in HARNESS_ROLES:
            continue
        HARNESS_ROLES.add(name)
        VARIANT_TO_BASE[f"{name}-heavy"] = name
        HEAVY_VARIANTS[name] = f"{name}-heavy"
        TIER_TABLE += f" | {name.capitalize()}=mid (inherit) ([heavy] task -> {name}-heavy/pro)"
    ALL_HARNESS_ROLE_TYPES = HARNESS_ROLES | set(VARIANT_TO_BASE.keys())


register_project_roles(discover_project_roles(_find_consumer_root()))


def _load_high_tier_keywords(default: tuple[str, ...] = ("opus",)) -> tuple[str, ...]:
    """Read HIGH_TIER_MODEL_KEYWORDS from harness.config.env, searching
    upward from cwd (same convention as .friday/active/harness/tools/_config.py). Kept as a
    tiny standalone reader rather than importing _config.py — this hook is
    deliberately dependency-free so it stays exercisable in isolation
    (see module docstring). Falls back to `default` if the config file or
    key is missing, so the hook still works before setup writes a config.
    """
    here = Path.cwd()
    for candidate in (here, *here.parents):
        config_path = candidate / "harness.config.env"
        if config_path.exists():
            for line in config_path.read_text(errors="ignore").splitlines():
                line = line.strip()
                if line.startswith("HIGH_TIER_MODEL_KEYWORDS="):
                    value = line.split("=", 1)[1].strip().strip('"').strip("'")
                    keywords = tuple(k.strip() for k in value.split(",") if k.strip())
                    return keywords or default
            return default
        if (candidate / ".git").exists():
            break
    return default


HIGH_TIER_KEYWORDS = _load_high_tier_keywords()

SPAWN_TOOL_NAMES = {"invoke_subagent", "Agent", "Task"}


def _allow(reason: str = "") -> dict:
    out = {"decision": "allow"}
    if reason:
        out["reason"] = reason
    return out


def _deny(reason: str) -> dict:
    return {
        "decision": "deny",
        "reason": reason,
    }


def get_base_role(type_name: str) -> str:
    """Map variant names like 'coder-heavy' -> 'coder'."""
    type_name_clean = type_name.strip().lower()
    return VARIANT_TO_BASE.get(type_name_clean, type_name_clean)


def build_title_regex(type_name: str) -> re.Pattern:
    """Matches `^<role>\\([^)]+\\):\\s+\\S`, case-insensitive.
    Allows either base role or variant name in the title, e.g.
    `coder(...)` or `coder-heavy(...)`."""
    base_role = get_base_role(type_name)
    escaped_base = re.escape(base_role)
    escaped_full = re.escape(type_name.strip().lower())
    if escaped_base != escaped_full:
        pattern = rf"^({escaped_base}|{escaped_full})\([^)]+\):\s+\S"
    else:
        pattern = rf"^{escaped_base}\([^)]+\):\s+\S"
    return re.compile(pattern, re.IGNORECASE)


def extract_model_tag(title: str, type_name: str) -> str:
    """'coder(<model>): build X' -> '<model>'."""
    base_role = get_base_role(type_name)
    escaped_base = re.escape(base_role)
    escaped_full = re.escape(type_name.strip().lower())
    m = re.match(rf"^({escaped_base}|{escaped_full})\(([^)]+)\):", title, re.IGNORECASE)
    return m.group(2).strip() if m else ""


def is_high_tier_model(model_name: str, model_tag: str) -> bool:
    combined = f"{model_name} {model_tag}".lower()
    return any(kw in combined for kw in HIGH_TIER_KEYWORDS)


def extract_subagent_specs(args: dict) -> list[dict]:
    """Extract normalized subagent specs from toolCall args."""
    # Format 1: Antigravity Subagents array
    for key in ("Subagents", "subagents"):
        if key in args and isinstance(args[key], list):
            specs = []
            for item in args[key]:
                if isinstance(item, dict):
                    specs.append({
                        "type_name": str(item.get("TypeName") or item.get("typeName") or item.get("name") or item.get("type") or "").strip(),
                        "role_title": str(item.get("Role") or item.get("role") or item.get("description") or "").strip(),
                        "prompt": str(item.get("Prompt") or item.get("prompt") or "").strip(),
                        "model": str(item.get("Model") or item.get("model") or "").strip(),
                    })
            return specs

    # Format 2: Single subagent dict args
    type_name = str(
        args.get("TypeName") or args.get("typeName") or args.get("agentName")
        or args.get("agent_name") or args.get("subagent_type") or args.get("name")
        or args.get("type") or ""
    ).strip()
    role_title = str(
        args.get("Role") or args.get("role") or args.get("description") or args.get("Description") or ""
    ).strip()
    prompt = str(
        args.get("Prompt") or args.get("prompt") or args.get("initialPrompt") or args.get("task") or ""
    ).strip()
    model = str(args.get("Model") or args.get("model") or "").strip()

    if type_name or role_title or prompt:
        return [{
            "type_name": type_name,
            "role_title": role_title,
            "prompt": prompt,
            "model": model,
        }]

    return []


def evaluate(payload: dict) -> dict:
    """Pure function: hook stdin payload -> hook stdout payload."""
    tool_call = payload.get("toolCall", {}) or {}
    tool_name = tool_call.get("name", "") or payload.get("tool_name", "")
    if tool_name not in SPAWN_TOOL_NAMES:
        return _allow()

    args = tool_call.get("args", {}) or payload.get("tool_input", {}) or {}
    subagents = extract_subagent_specs(args)

    if not subagents:
        # Unable to parse subagent specs — fail open
        return _allow()

    warnings = []

    for spec in subagents:
        type_name = spec["type_name"].lower()
        role_title = spec["role_title"]
        prompt = spec["prompt"]
        model = spec["model"]

        # Wrong-type guard: a `role(model): task` title for a harness role
        # spawned as general-purpose/missing/any non-role type means the role's
        # agent file (tool allowlist, model, harness preamble) is being
        # bypassed. Deny (exit 2) rather than ask: the title is an unambiguous
        # statement of intent and utility spawns never use a role-shaped title.
        # NOTE: this cannot catch a session launched outside the project root --
        # the hook (and the agent types) are not loaded there; the Controller's
        # "Session start check" covers that case.
        if type_name not in ALL_HARNESS_ROLE_TYPES:
            m = re.match(r"^([a-z][a-z0-9_-]*)\([^)]+\):\s+\S", role_title)
            if m and m.group(1) in ALL_HARNESS_ROLE_TYPES:
                return _deny(
                    f"Spawn title {role_title!r} names harness role {m.group(1)!r} but "
                    f"subagent_type is {type_name or '(missing)'!r}. Spawn with "
                    f"subagent_type={m.group(1)!r} so the role's agent file applies "
                    "(tools, model, harness preamble). If that type is not available, "
                    "the session was launched outside the project root: stop and ask "
                    "the user to restart with `cd <project root> && claude --agent controller`."
                )
            # Utility spawns (e.g. search, bash helpers, etc.) are exempt
            continue

        base_role = get_base_role(type_name)

        # 1. Title format check
        if not build_title_regex(type_name).match(role_title):
            return _deny(
                f"Spawn TypeName={type_name!r} is a harness role but Role/title "
                f"{role_title!r} does not match the required 'role(model): task' format "
                f"(regex: ^{base_role}\\([^)]+\\):\\s+\\S). "
                f"e.g. `{base_role}(<model>): <task>`. Tier table: {TIER_TABLE}. "
                "Retry with a correctly formatted Role/title, choosing the model per the "
                "tier table and the task's [light]/[heavy] tag."
            )

        # 2. Advisory check on [heavy] escalation
        if "[heavy]" in prompt:
            heavy_variant = HEAVY_VARIANTS.get(base_role)
            model_tag = extract_model_tag(role_title, type_name)
            is_escalated = (
                type_name == heavy_variant
                or is_high_tier_model(model, model_tag)
            )

            if heavy_variant and not is_escalated:
                warnings.append(
                    f"SOFT WARNING (check_agent_spawn): invoked '{type_name}' with '[heavy]' "
                    f"tag in prompt, but model is not high tier (Antigravity: variant '{heavy_variant}' / model 'pro'; Claude: pass a high-tier model explicitly). "
                    f"Tier table: {TIER_TABLE}. Advisory only — not blocked."
                )

    if warnings:
        return _allow(reason="; ".join(warnings))

    return _allow()


def main() -> int:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, OSError):
        print(json.dumps(_allow(reason="check_agent_spawn: unparseable stdin, failed open")))
        return 0

    result = evaluate(payload)
    if result.get("decision") == "deny" and (
        payload.get("hook_event_name") == "PreToolUse" or "tool_name" in payload
    ):
        # Claude Code ignores a JSON "deny" from this hook for Agent spawns
        # (verified live); exit code 2 + stderr is what actually blocks and
        # feeds the reason back to the model. Antigravity reads the JSON.
        print(result["reason"], file=sys.stderr)
        return 2
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
