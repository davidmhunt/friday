#!/usr/bin/env python3
"""PreToolUse hook on the subagent-spawn tool (`invoke_subagent`) —
Antigravity CLI port of `.claude/hooks/check_agent_spawn.py`.

Mechanically enforces the spawn-title convention (harness/harness.md §Dispatch,
harness/rules/conventions.md §Spawn titles).

Hard-blocks a role spawn whose title / Role isn't `role(model): task`, and
soft-warns when a `[heavy]`-tagged spawn is invoked without high-tier escalation
(e.g. invoking base `coder` instead of `coder-heavy` or without `pro` model).
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
HARNESS_ROLES = {"controller", "planner", "coder", "runner", "reviewer", "author", "researcher"}

# Map each variant name back to its base harness role
VARIANT_TO_BASE = {
    "planner-heavy": "planner",
    "coder-heavy": "coder",
    "runner-judgment": "runner",
    "reviewer-heavy": "reviewer",
    "researcher-heavy": "researcher",
    "researcher-quick": "researcher",
}

# Map base roles to their high-tier [heavy] escalation variant
HEAVY_VARIANTS = {
    "planner": "planner-heavy",
    "coder": "coder-heavy",
    "reviewer": "reviewer-heavy",
    "researcher": "researcher-heavy",
}

ALL_HARNESS_ROLE_TYPES = HARNESS_ROLES | set(VARIANT_TO_BASE.keys())

TIER_TABLE = (
    "Controller=mid (inherit) | Planner=mid (inherit) ([heavy] task -> planner-heavy/pro) | "
    "Coder=mid (inherit) ([heavy] task -> coder-heavy/pro) | "
    "Runner=light (flash) (judgment -> runner-judgment/inherit) | "
    "Reviewer=mid (inherit) ([heavy] task -> reviewer-heavy/pro) | Author=mid (inherit) | "
    "Researcher=mid (inherit) ([heavy]/proof-bearing task -> researcher-heavy/pro; "
    "quick lookup -> researcher-quick/inherit)"
)

def _load_high_tier_keywords(default: tuple[str, ...] = ("opus",)) -> tuple[str, ...]:
    """Read HIGH_TIER_MODEL_KEYWORDS from harness.config.env, searching
    upward from cwd (same convention as harness/tools/_config.py). Kept as a
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

        # Utility spawns (e.g. search, bash helpers, etc.) are exempt
        if type_name not in ALL_HARNESS_ROLE_TYPES:
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
                    f"tag in prompt, but model is not high tier (variant '{heavy_variant}' / model 'pro'). "
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

    print(json.dumps(evaluate(payload)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
