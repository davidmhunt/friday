#!/usr/bin/env python3
"""Antigravity PreToolUse hook for command permission guarding.

Evaluates CommandLine against project policies:
- "allow": Safe, read-only, tests, docs compilation, or package-manager sync.
- "force_ask": Modifying commands (git commit/push, dependency add/remove, systemd-run, rm, unclassified).
- "deny": Strictly forbidden destructive commands (sudo, rm -rf /, git push --force).

The generic patterns below (deny list, git read-only inspection, basic file
inspection/navigation, and the modifying-command force-ask list) are
project-independent and stay hardcoded. The package-manager/test/LaTeX allow
patterns and the dependency-add/remove force-ask patterns are project
-specific, so they're derived at import time from `harness.config.env`
(PACKAGE_MANAGER*, TEST_CMD, LATEX_DRAFTING_ENABLED) via a tiny standalone
upward-search reader — the same pattern `check_agent_spawn.py` uses for
`_load_high_tier_keywords()` — rather than importing `.friday/active/harness/tools/
_config.py`, so this hook stays dependency-free and exercisable standalone
(this file is a shared symlink into every consumer project's
`.claude/hooks/` / Antigravity hooks dir; the config it reads is per-project,
found by searching upward from cwd). If `harness.config.env` is missing or
doesn't carry usable package-manager keys (e.g. before setup has run), this
falls back to the original hardcoded `uv` + LaTeX patterns so behavior never
regresses.
"""

import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Manager name -> verb used for its "remove a dependency" subcommand. Used to
# build a force-ask pattern from PACKAGE_MANAGER alone, without requiring a
# dedicated PACKAGE_MANAGER_REMOVE_CMD config key.
_REMOVE_VERB_BY_MANAGER = {
    "uv": "remove",
    "pip": "uninstall",
    "pip3": "uninstall",
    "poetry": "remove",
    "npm": "uninstall",
    "yarn": "remove",
    "pnpm": "remove",
}

# Read-only / lockfile-refresh subcommands that are safe to auto-allow
# alongside the sync/run/test commands derived from config. These don't fall
# out of any harness.config.env key (the interview only captures sync/run/
# add/test), but the hardcoded list this replaced did allow `uv lock`, and
# dropping it would silently start prompting for a routine no-op.
_SAFE_VERBS_BY_MANAGER = {
    "uv": ("lock",),
    "poetry": ("lock", "check"),
    "npm": ("ci",),
    "pnpm": ("install --frozen-lockfile",),
}

# Fail-safe default: today's exact uv + LaTeX literals, used whenever
# harness.config.env is missing, unreadable, or carries none of the relevant
# package-manager/test keys (i.e. "unparseable" for our purposes).
_DEFAULT_ALLOW_EXTRA = [
    r"^uv\s+(sync|lock|--version|-V)(\s+.*)?$",
    r"^(uv\s+run\s+)?pytest(\s+.*)?$",
    r"^(uv\s+run\s+)?python[3]?(\s+.*)?$",
    r"^(latexmk|bibtex|pdflatex|xelatex|lualatex)(\s+.*)?$",
]
_DEFAULT_FORCE_ASK_EXTRA = [
    (r"\buv\s+(add|remove)\b", "Modifying project dependencies requires confirmation."),
]


def _read_config_file(config_path: Path) -> Dict[str, str]:
    values: Dict[str, str] = {}
    for line in config_path.read_text(errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _load_project_command_config(start: Optional[Path] = None) -> Dict[str, str]:
    """Read the handful of package-manager/test/LaTeX keys this hook cares
    about from `harness.config.env`, searching upward — same convention as
    `.friday/active/harness/tools/_config.py` and `check_md_hygiene.py`'s
    `find_repo_root()`. Kept as a tiny standalone reader rather than
    importing either of those (see module docstring).

    Two start points are tried, in order: cwd (these hooks are documented and
    wired to run from the consumer repo root), then the *unresolved*
    `Path(__file__).parent` — i.e. the symlink's own directory
    (`.agents/hooks/`), not its resolved target inside `.friday/`.

    The second start point is what makes this correct when cwd happens to sit
    inside `.friday/` (an agent that cd'd into the submodule, a test runner).
    An earlier version stopped the walk at the first directory containing a
    `.git` entry, which in a submodule is a *file* — so a cwd inside
    `.friday/` hit that boundary, found no config, and silently fell back to
    the `uv`+LaTeX defaults below. On a project that uses neither, that
    quietly auto-allowed `uv sync` and `latexmk` while pushing the project's
    real commands to force_ask. A guardrail applying another project's policy
    is worse than one that's merely absent, so there is deliberately no
    early boundary break here: an upward walk that finds no
    `harness.config.env` at all falls through to the safe defaults anyway.
    """
    starts = [start] if start is not None else [Path.cwd(), Path(__file__).parent]
    for begin in starts:
        for candidate in (begin, *begin.parents):
            config_path = candidate / "harness.config.env"
            if config_path.exists():
                return _read_config_file(config_path)
    return {}


_ENV_ASSIGNMENT_PREFIX_RE = re.compile(r"^(?:[A-Za-z_][A-Za-z0-9_]*=\S*\s+)+")


def strip_env_assignments(cmd: str) -> str:
    """Drop leading `VAR=value` tokens from a command line.

    A perfectly ordinary TEST_CMD carries an environment prefix — this
    project's is `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run pytest`. Without
    stripping it, two things silently go wrong: the literal allow pattern
    built from TEST_CMD only matches when the caller reproduces the prefix
    verbatim, and the bare-runner derivation below (which asks whether
    TEST_CMD is RUN_CMD plus a runner) never fires, so a bare `pytest`
    starts prompting — exactly the regression that derivation exists to
    prevent.
    """
    return _ENV_ASSIGNMENT_PREFIX_RE.sub("", cmd).strip()


def build_dynamic_patterns(config: Dict[str, str]) -> Tuple[List[str], List[Tuple[str, str]]]:
    """Pure function: parsed harness.config.env dict -> (extra allow
    patterns, extra force-ask (pattern, reason) pairs). Separated from
    `_load_project_command_config()` so it's directly unit-testable with
    fabricated config dicts, independent of the real filesystem/cwd.
    """
    sync_cmd = config.get("PACKAGE_MANAGER_SYNC_CMD", "").strip()
    run_cmd = config.get("PACKAGE_MANAGER_RUN_CMD", "").strip()
    add_cmd = config.get("PACKAGE_MANAGER_ADD_CMD", "").strip()
    test_cmd = config.get("TEST_CMD", "").strip()
    manager = config.get("PACKAGE_MANAGER", "").strip().lower()
    latex_enabled = config.get("LATEX_DRAFTING_ENABLED", "").strip().lower() == "true"

    if not (sync_cmd or run_cmd or test_cmd):
        # No usable project-command keys: config missing/unparseable for our
        # purposes. Fall back to the historical hardcoded uv+LaTeX behavior
        # so the hook never regresses and still works before setup runs.
        return list(_DEFAULT_ALLOW_EXTRA), list(_DEFAULT_FORCE_ASK_EXTRA)

    allow: List[str] = []
    force_ask: List[Tuple[str, str]] = []

    for cmd in (sync_cmd, run_cmd, test_cmd):
        if not cmd:
            continue
        allow.append(rf"^{re.escape(cmd)}(\s+.*)?$")
        # Allow the command with its env prefix dropped too, so a config
        # whose TEST_CMD is `FOO=1 uv run pytest` doesn't force-ask the
        # plain `uv run pytest` that everyone actually types.
        stripped = strip_env_assignments(cmd)
        if stripped and stripped != cmd:
            allow.append(rf"^{re.escape(stripped)}(\s+.*)?$")

    # When TEST_CMD is just RUN_CMD plus a runner (`uv run pytest`), allow the
    # bare runner too (`pytest`). The hardcoded list this replaced matched
    # `^(uv\s+run\s+)?pytest`, i.e. both forms; deriving only from TEST_CMD
    # would quietly start prompting for a bare `pytest`. Managers whose test
    # command isn't prefixed by the run command (`npm test` vs `npm run`) get
    # no bare form, which is correct — there's no separate runner to name.
    # A leading env-var prefix on TEST_CMD is stripped first; it describes
    # how the tests are run, not which runner runs them.
    bare_test_cmd = strip_env_assignments(test_cmd)
    if bare_test_cmd and run_cmd and bare_test_cmd.startswith(run_cmd + " "):
        bare_runner = bare_test_cmd[len(run_cmd) :].strip()
        if bare_runner:
            allow.append(rf"^{re.escape(bare_runner)}(\s+.*)?$")
    if manager:
        allow.append(rf"^{re.escape(manager)}\s+(--version|-V)$")
        for verb in _SAFE_VERBS_BY_MANAGER.get(manager, ()):
            allow.append(rf"^{re.escape(manager)}\s+{re.escape(verb)}(\s+.*)?$")

    if add_cmd:
        force_ask.append((rf"\b{re.escape(add_cmd)}\b", "Modifying project dependencies requires confirmation."))
    if manager:
        remove_verb = _REMOVE_VERB_BY_MANAGER.get(manager, "remove")
        force_ask.append((
            rf"\b{re.escape(manager)}\s+{re.escape(remove_verb)}\b",
            "Modifying project dependencies requires confirmation.",
        ))

    if latex_enabled:
        allow.append(r"^(latexmk|bibtex|pdflatex|xelatex|lualatex)(\s+.*)?$")

    return allow, force_ask


_PROJECT_COMMAND_CONFIG = _load_project_command_config()
_EXTRA_ALLOW_PATTERNS, _EXTRA_FORCE_ASK_PATTERNS = build_dynamic_patterns(_PROJECT_COMMAND_CONFIG)

# DENY is the ONLY layer that still applies in container mode (see
# evaluate_subcommand), so every hole here is a hole in the container's whole
# policy. Several of these patterns exist specifically because container mode
# removed the force-ask net that used to catch them incidentally on the host.
DENY_PATTERNS = [
    (r"\b(sudo|su|doas)\b", "Privilege escalation is forbidden."),
    (r"\bchmod\s+(-R\s+)?(777|a\+rwx)\b", "Insecure permissions change (777) is forbidden."),
    # Targets that wipe something the caller almost certainly didn't scope:
    # an absolute path, $HOME, the cwd, the PARENT of the cwd, or a bare
    # leading glob. `..` and `*` matter more than they look inside the dev
    # container: the host repo is bind-mounted at /<project name>, so `rm -rf ..`
    # from any subdirectory deletes real host files. Interposed flags
    # (e.g. `--no-preserve-root`) must not let the target slip past.
    (r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f[a-zA-Z]*\s+(?:--?\S+\s+)*([/~]|\.\.|\.\s*$|\.\/(?:\*|\s|$)|\*)", "Destructive filesystem wipe is forbidden."),
    (r"\bgit\s+push\b.*(\s+--force\b|\s+-f\b)", "Force-pushing to git remote is forbidden."),
    # `git push origin +main` is a force-push in refspec notation — same
    # destructive effect as --force, none of the same spelling.
    (r"\bgit\s+push\b[^|;&]*\s\+[\w./*-]+", "Force-pushing via +refspec is forbidden."),
    # The container forwards the HOST's ssh-agent socket and ~/.gitconfig, so
    # a push to a newly added remote exfiltrates the repo under the operator's
    # real identity. Adding the remote is the step worth stopping.
    (r"\bgit\s+remote\s+add\b", "Adding a new git remote is forbidden (the container carries the host's ssh identity)."),
    (r"\bgit\s+clean\b.*(\s+-f|\s+--force)", "Destructive git clean is forbidden."),
    # Remote-code-execution shapes. The literal `curl ... | bash` pipe was the
    # only form caught before, and split_compound_commands defeated it: the
    # halves of `curl -o /tmp/x && sh /tmp/x` are innocuous on their own, so
    # only a check against the RAW command line can see the pair. These run
    # top-level in evaluate_command_line, before any splitting.
    (r"(?s)\b(curl|wget)\b.*(\||;|&&)\s*(bash|sh|zsh)\b", "Piping or chaining remote web scripts into a shell is forbidden."),
    (r"(?s)\beval\b.*\$\(.*\b(curl|wget)\b", "Evaluating the output of a remote fetch is forbidden."),
    (r"\b(mkfs|dd\s+if=)", "Direct disk formatting / raw writing is forbidden."),
]

FORCE_ASK_PATTERNS = [
    (r"\bgit\s+(commit|push|checkout|switch|reset|stash|merge|rebase|tag|cherry-pick|revert)\b", "Git branch/remote state modification requires confirmation."),
    (r"\b(systemd-run|setsid)\b", "Launching detached/background service requires confirmation."),
    (r"\bpip\s+(install|uninstall)\b", "Package installation/removal requires confirmation."),
    (r"\b(rm|unlink|rmdir)\b", "File deletion requires confirmation."),
    (r"\bmv\b", "Moving or renaming files requires confirmation."),
    (r"\b(kill|pkill|killall)\b", "Terminating processes requires confirmation."),
    (r"\bsed\s+-i", "In-place file modification via sed requires confirmation."),
] + _EXTRA_FORCE_ASK_PATTERNS

ALLOW_COMMAND_PATTERNS = [
    # git read-only inspection operations
    r"^git\s+(status|diff|log|show|branch|rev-parse|describe|remote|ls-files|check-ignore|check-attr|version)(\s+.*)?$",
    # curl / http requests (safe, not piped to bash)
    r"^curl\s+.*$",
    # basic inspection & navigation
    r"^(ls|dir|pwd|cat|head|tail|grep|rg|find|which|whereis|echo|diff|colordiff|wc|sort|uniq|cut|awk|tree|file|stat|du|df|env|printenv|uname|whoami|date|uptime)(\s+.*)?$",
    # tool version checks
    r"^(python|python3|jupyter|node|git|latexmk)\s+(--version|-V|-v)$",
] + _EXTRA_ALLOW_PATTERNS


def unwrap_command_strings(command_line: str) -> List[str]:
    """Extract nested commands if wrapped in bash -c '...' or sh -c '...'."""
    cmd = command_line.strip()
    if not cmd:
        return []

    # Check for bash -c / sh -c wrapper
    wrapper_match = re.search(r"^(?:bash|sh)\s+-c\s+(['\"])(.*?)\1\s*$", cmd, re.DOTALL)
    if wrapper_match:
        inner_cmd = wrapper_match.group(2).strip()
        return split_compound_commands(inner_cmd)
    
    return split_compound_commands(cmd)


def split_compound_commands(cmd: str) -> List[str]:
    """Split commands on ;, &&, ||, |, and newlines while respecting basic structure."""
    lines = [line.strip() for line in cmd.splitlines() if line.strip()]
    if not lines:
        return []

    sub_commands: List[str] = []
    for line in lines:
        tokens = re.split(r"(?:&&|\|\||;|\|)", line)
        for token in tokens:
            cleaned = token.strip()
            # Remove leading/trailing redirects or background ampersand
            cleaned = re.sub(r">\s*\S+", "", cleaned)
            cleaned = re.sub(r"<\s*\S+", "", cleaned)
            cleaned = re.sub(r"2>&1", "", cleaned)
            cleaned = re.sub(r"&\s*$", "", cleaned).strip()
            if cleaned and cleaned not in ("disown", "true", "false"):
                sub_commands.append(cleaned)
    return sub_commands


def is_container_environment() -> bool:
    """Whether to run in container mode: deny-list only, no force-ask.

    Deliberately keyed ONLY to environment variables this project's own
    docker-compose.yml sets. An earlier version also treated the presence of
    /.dockerenv as sufficient, which is wrong: that file exists in *any*
    container — a VS Code devcontainer, a Docker-based CI job, a nested
    `docker run` — and each of those would have silently dropped the guard to
    deny-list-only somewhere the operator never opted in.
    """
    return (
        os.getenv("ANTIGRAVITY_CONTAINER") == "1"
        or os.getenv("CONTAINER_AUTO_ALLOW") == "1"
    )


def evaluate_subcommand(sub_cmd: str, in_container: bool = False) -> Tuple[str, Optional[str]]:
    """Evaluate a single sub-command and return (decision, reason)."""
    # 1. Deny check (always active, in container and on host)
    for pattern, reason in DENY_PATTERNS:
        if re.search(pattern, sub_cmd):
            return "deny", reason

    # In container mode: all non-denied commands are auto-allowed for autonomous execution
    if in_container:
        return "allow", None

    # 2. Force-ask check (host mode)
    for pattern, reason in FORCE_ASK_PATTERNS:
        if re.search(pattern, sub_cmd):
            return "force_ask", reason

    # 3. Allow check (host mode)
    for pattern in ALLOW_COMMAND_PATTERNS:
        if re.match(pattern, sub_cmd):
            return "allow", None

    # 4. Default for unrecognized commands (host mode)
    return "force_ask", f"Command '{sub_cmd}' is not in the auto-allow list and requires confirmation."


def evaluate_command_line(command_line: str, in_container: Optional[bool] = None) -> Dict[str, str]:
    """Evaluate the entire command line."""
    if not command_line or not command_line.strip():
        return {"decision": "allow"}

    container_mode = is_container_environment() if in_container is None else in_container

    # 1. Top-level Deny check across entire raw string (catches pipelines like curl | bash)
    for pattern, reason in DENY_PATTERNS:
        if re.search(pattern, command_line):
            return {"decision": "deny", "reason": reason}

    sub_commands = unwrap_command_strings(command_line)
    if not sub_commands:
        return {"decision": "allow"}

    highest_ask_reason = None

    for sub_cmd in sub_commands:
        decision, reason = evaluate_subcommand(sub_cmd, in_container=container_mode)
        if decision == "deny":
            return {"decision": "deny", "reason": reason or "Command is strictly forbidden by policy."}
        if decision == "force_ask":
            if not highest_ask_reason:
                highest_ask_reason = reason

    if highest_ask_reason:
        return {"decision": "force_ask", "reason": highest_ask_reason}

    return {"decision": "allow"}


def main():
    try:
        raw_input = sys.stdin.read()
        if not raw_input.strip():
            print(json.dumps({"decision": "allow"}))
            return

        payload = json.loads(raw_input)
        command_line = payload.get("toolCall", {}).get("args", {}).get("CommandLine", "")
        result = evaluate_command_line(command_line)
        print(json.dumps(result))
    except Exception as e:
        # Fallback safely to force_ask on unexpected hook failure
        print(json.dumps({
            "decision": "force_ask",
            "reason": f"Permission hook encountered an evaluation error: {str(e)}"
        }))


if __name__ == "__main__":
    main()
