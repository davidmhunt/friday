#!/usr/bin/env python3
"""Antigravity PreToolUse hook for command permission guarding.

Evaluates CommandLine against project policies:
- "allow": Safe, read-only, tests, docs compilation, or uv sync.
- "force_ask": Modifying commands (git commit/push, uv add, systemd-run, rm, unclassified).
- "deny": Strictly forbidden destructive commands (sudo, rm -rf /, git push --force).
"""

import json
import re
import sys
from typing import Dict, List, Optional, Tuple

DENY_PATTERNS = [
    (r"\b(sudo|su|doas)\b", "Privilege escalation is forbidden."),
    (r"\bchmod\s+(-R\s+)?(777|a\+rwx)\b", "Insecure permissions change (777) is forbidden."),
    (r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f[a-zA-Z]*\s+([/~]|\.\s*$|\.\/|\/\*)", "Destructive filesystem wipe is forbidden."),
    (r"\bgit\s+push\b.*(\s+--force\b|\s+-f\b)", "Force-pushing to git remote is forbidden."),
    (r"\bgit\s+clean\b.*(\s+-f|\s+--force)", "Destructive git clean is forbidden."),
    (r"\b(curl|wget)\b.*\|\s*(bash|sh)\b", "Piping remote web scripts to shell is forbidden."),
    (r"\b(mkfs|dd\s+if=)", "Direct disk formatting / raw writing is forbidden."),
]

FORCE_ASK_PATTERNS = [
    (r"\bgit\s+(commit|push|checkout|switch|reset|stash|merge|rebase|tag|cherry-pick|revert)\b", "Git branch/remote state modification requires confirmation."),
    (r"\b(systemd-run|setsid)\b", "Launching detached/background service requires confirmation."),
    (r"\buv\s+(add|remove)\b", "Modifying project dependencies requires confirmation."),
    (r"\bpip\s+(install|uninstall)\b", "Package installation/removal requires confirmation."),
    (r"\b(rm|unlink|rmdir)\b", "File deletion requires confirmation."),
    (r"\bmv\b", "Moving or renaming files requires confirmation."),
    (r"\b(kill|pkill|killall)\b", "Terminating processes requires confirmation."),
    (r"\bsed\s+-i", "In-place file modification via sed requires confirmation."),
]

ALLOW_COMMAND_PATTERNS = [
    # uv sync / version
    r"^uv\s+(sync|lock|--version|-V)(\s+.*)?$",
    # pytest / tests
    r"^(uv\s+run\s+)?pytest(\s+.*)?$",
    # uv run python / scripts
    r"^(uv\s+run\s+)?python[3]?(\s+.*)?$",
    # latex compilation
    r"^(latexmk|bibtex|pdflatex|xelatex|lualatex)(\s+.*)?$",
    # git read-only inspection operations
    r"^git\s+(status|diff|log|show|branch|rev-parse|describe|remote|ls-files|check-ignore|check-attr|version)(\s+.*)?$",
    # curl / http requests (safe, not piped to bash)
    r"^curl\s+.*$",
    # basic inspection & navigation
    r"^(ls|dir|pwd|cat|head|tail|grep|rg|find|which|whereis|echo|diff|colordiff|wc|sort|uniq|cut|awk|tree|file|stat|du|df|env|printenv|uname|whoami|date|uptime)(\s+.*)?$",
    # tool version checks
    r"^(python|python3|jupyter|node|git|latexmk)\s+(--version|-V|-v)$",
]


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


def evaluate_subcommand(sub_cmd: str) -> Tuple[str, Optional[str]]:
    """Evaluate a single sub-command and return (decision, reason)."""
    # 1. Deny check
    for pattern, reason in DENY_PATTERNS:
        if re.search(pattern, sub_cmd):
            return "deny", reason

    # 2. Force-ask check
    for pattern, reason in FORCE_ASK_PATTERNS:
        if re.search(pattern, sub_cmd):
            return "force_ask", reason

    # 3. Allow check
    for pattern in ALLOW_COMMAND_PATTERNS:
        if re.match(pattern, sub_cmd):
            return "allow", None

    # 4. Default for unrecognized commands
    return "force_ask", f"Command '{sub_cmd}' is not in the auto-allow list and requires confirmation."


def evaluate_command_line(command_line: str) -> Dict[str, str]:
    """Evaluate the entire command line."""
    if not command_line or not command_line.strip():
        return {"decision": "allow"}

    # 1. Top-level Deny check across entire raw string (catches pipelines like curl | bash)
    for pattern, reason in DENY_PATTERNS:
        if re.search(pattern, command_line):
            return {"decision": "deny", "reason": reason}

    sub_commands = unwrap_command_strings(command_line)
    if not sub_commands:
        return {"decision": "allow"}

    highest_ask_reason = None

    for sub_cmd in sub_commands:
        decision, reason = evaluate_subcommand(sub_cmd)
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
