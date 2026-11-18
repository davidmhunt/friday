#!/usr/bin/env python3
"""friday's hooks: one script, one subcommand per event. Standard library only.

  pretool      PreToolUse on Bash: deny list, ./run enforcement, commit trailer, hardware gate
  stop         Stop: while a directive is active in this worktree, its Verify: must pass
  session-end  SessionEnd: release this session's hardware leases
  posttool     PostToolUse on Write|Edit|MultiEdit: a goal/directive file's own format errors go
               back to the model (stderr, exit 2); warnings and clean files are silent

Every decision is deterministic and explained in its reason, so the agent learns the fix from
the refusal. Malformed input fails open (no decision): a hook bug must never wedge a session.
The rules and where they came from: docs/workflow.md ("Hooks") and docs/migrating-from-v0.md.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
import friday_core as fc  # noqa: E402

# ------------------------------------------------------------------ deny list
# Ported from v0.20's command_guard.py, where each line traces to an incident or a hard rule.
DENY = [
    (r"(^|[\s;&|(])(sudo|su|doas)(\s|$)", "Privilege escalation is not allowed from an agent session; ask the user to run it."),
    (r"\bchmod\s+(-R\s+)?(777|a\+rwx)\b", "chmod 777 / a+rwx is not allowed."),
    (r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f[a-zA-Z]*\s+(?:--?\S+\s+)*([/~]|\.\.|\.\s*$|\./(?:\*|\s|$)|\*)",
     "Unscoped rm -rf (/, ~, ., .., or a bare *) is not allowed; name the exact path."),
    (r"\bgit\s+push\b.*(\s--force\b|\s--force-with-lease\b|\s-f\b)", "Force-push is not allowed."),
    (r"\bgit\s+push\b[^|;&]*\s\+[\w./*-]+", "Force-push via +refspec is not allowed."),
    (r"\bgit\s+push\b[^|;&]*\s(origin\s+)?(HEAD:)?(main|master)(\s|$)", "Pushing to main/master is not allowed; push the directive branch and open a PR."),
    (r"\bgit\s+remote\s+add\b", "Adding a git remote is not allowed."),
    (r"\bgit\s+clean\b.*(\s-[a-zA-Z]*f|\s--force)", "git clean -f is not allowed."),
    (r"(?s)\b(curl|wget)\b.*(\||;|&&)\s*(bash|sh|zsh)\b", "Piping a downloaded script into a shell is not allowed."),
    (r"(?s)\beval\b.*\$\(.*\b(curl|wget)\b", "Evaluating fetched content is not allowed."),
    (r"\b(mkfs(\.\w+)?|dd\s+if=)", "Raw disk writes are not allowed."),
]

DECISION_RANK = {"deny": 3, "ask": 2, "allow": 1}


def _emit_pretool(decision: str, reason: str) -> None:
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                             "permissionDecision": decision,
                                             "permissionDecisionReason": reason}}))


def check_deny(cmd: str) -> str | None:
    for pat, reason in DENY:
        if re.search(pat, cmd):
            return reason
    return None


def check_run_only(cmd: str, cfg: dict) -> str | None:
    tools = set(cfg.get("run_only") or [])
    wrapper = cfg.get("run_wrapper", "./run")
    if not tools:
        return None
    for simple in fc.split_commands(cmd):
        argv = fc.argv_of(simple)
        if not argv:
            continue
        if argv[0] in (wrapper, Path(wrapper).name) or argv[0].endswith("/run"):
            continue
        if Path(argv[0]).name in tools:
            return (f"In this project, builds, tests and scripts run through `{wrapper}` "
                    f"(dev container or native, per machine). Use: {wrapper} {simple.strip()}")
    return None


def _commit_message(argv: list[str], cwd: Path) -> str | None:
    """Text of -m/--message/-F/--file args of a `git commit` argv, or None when an editor would open."""
    def from_file(path: str) -> str:
        try:
            return (cwd / path).read_text() if path != "-" else ""
        except OSError:
            return ""

    msgs, i, saw = [], 0, False
    while i < len(argv):
        a = argv[i]
        if a in ("-m", "--message") and i + 1 < len(argv):
            msgs.append(argv[i + 1]); saw = True; i += 2; continue
        if a in ("-F", "--file") and i + 1 < len(argv):
            msgs.append(from_file(argv[i + 1])); saw = True; i += 2; continue
        if a.startswith("--message="):
            msgs.append(a.split("=", 1)[1]); saw = True
        elif a.startswith("--file="):
            msgs.append(from_file(a.split("=", 1)[1])); saw = True
        elif a.startswith("-m") and len(a) > 2:
            msgs.append(a[2:]); saw = True
        elif a.startswith("-F") and len(a) > 2:
            msgs.append(from_file(a[2:])); saw = True
        elif a in ("--no-edit", "-C", "-c", "--reuse-message", "--reedit-message", "--amend"):
            saw = saw or a != "--amend"
        i += 1
    return "\n".join(msgs) if saw else None


def check_commit(cmd: str, cwd: Path) -> tuple[str, str] | None:
    """Agent commits during a directive carry a `Directive: <id>` trailer and never land on main."""
    marker = fc.read_marker(cwd)
    for simple in fc.split_commands(cmd):
        argv = fc.argv_of(simple)
        if len(argv) < 2 or argv[0] != "git":
            continue
        rest = argv[1:]
        while rest and rest[0] in ("-C", "-c") and len(rest) > 1:   # git -C dir commit ...
            rest = rest[2:]
        if not rest or rest[0] != "commit":
            continue
        branch = fc.current_branch(cwd)
        if branch in ("main", "master"):
            if marker:
                return "deny", f"Directive {marker['id']} commits go on its own branch, not {branch}. Create or switch to friday/{marker['id']}."
            return "ask", f"Commit directly on {branch}?"
        if marker:
            msg = _commit_message(rest[1:], cwd)
            if msg is not None and not re.search(rf"(?m)^Directive:\s*{re.escape(marker['id'])}\s*$", msg):
                return "deny", (f"Commits for directive {marker['id']} end with the trailer line "
                                f"`Directive: {marker['id']}` (add -m \"Directive: {marker['id']}\").")
    return None


def check_hardware(cmd: str, cfg: dict, session: str) -> tuple[str, str] | None:
    hw = cfg.get("hardware") or {}
    for resource, patterns in hw.items():
        if not any(re.search(p, cmd) for p in patterns):
            continue
        holder = fc.lease_holder(resource)
        if holder and holder.get("session") != session:
            age = int((time.time() - holder["time"]) / 60)
            return "deny", (f"Hardware `{resource}` is held by another session on {holder.get('host')} "
                            f"({age} min ago: {holder.get('note', '')}). Wait, or ask the user to run "
                            f"`friday release {resource}`.")
        fc.take_lease(resource, session, cmd)
        return "ask", f"Hardware `{resource}`: this command touches a physical device. Lease taken for this session."
    return None


def pretool(payload: dict) -> None:
    if payload.get("tool_name") != "Bash":
        return
    cmd = (payload.get("tool_input") or {}).get("command") or ""
    cwd = Path(payload.get("cwd") or ".")
    root = fc.repo_root(cwd)
    cfg = fc.load_config(root)
    results: list[tuple[str, str]] = []
    if (r := check_deny(cmd)):
        results.append(("deny", r))
    if (r := check_run_only(cmd, cfg)):
        results.append(("deny", r))
    if (r := check_commit(cmd, cwd)):
        results.append(r)
    if not any(d == "deny" for d, _ in results) and (r := check_hardware(cmd, cfg, payload.get("session_id", ""))):
        results.append(r)
    if results:
        decision = max(results, key=lambda r: DECISION_RANK[r[0]])[0]
        _emit_pretool(decision, " ".join(r for d, r in results if d == decision))


# ------------------------------------------------------------------ stop gate
MAX_STOP_BLOCKS = 3


def stop(payload: dict) -> None:
    cwd = Path(payload.get("cwd") or ".")
    marker = fc.read_marker(cwd)
    if not marker or not marker.get("gate", True):
        return
    if payload.get("background_tasks"):        # a workflow or job is still running: not done yet
        return
    root = fc.repo_root(cwd)
    d = fc.read_directive(root, marker["id"]) if root else None
    if not d or not d.get("verify"):
        return
    if d["verify"].strip().lower() == "none":
        print(json.dumps({"systemMessage": f"friday: Verify for {marker['id']} is none, not run."}))
        return
    counter = fc.git_dir(cwd) / "friday-stop-blocks"
    try:
        out = subprocess.run(d["verify"], shell=True, cwd=root, capture_output=True, text=True, timeout=1800)
        ok, tail = out.returncode == 0, (out.stdout + out.stderr)[-4000:]
    except subprocess.TimeoutExpired:
        ok, tail = False, "Verify timed out after 30 min."
    if ok:
        counter.unlink(missing_ok=True)
        return
    n = int(counter.read_text()) + 1 if counter.exists() else 1
    if n > MAX_STOP_BLOCKS:
        counter.unlink(missing_ok=True)
        print(json.dumps({"systemMessage": f"friday: Verify for {marker['id']} still fails after "
                                           f"{MAX_STOP_BLOCKS} attempts; stopping for the user."}))
        return
    counter.write_text(str(n))
    print(json.dumps({"decision": "block",
                      "reason": (f"Directive {marker['id']} is not done: its Verify command "
                                 f"`{d['verify']}` fails (attempt {n}/{MAX_STOP_BLOCKS}). Fix the root "
                                 f"cause, or run `friday finish {marker['id']} --blocked \"<why>\"` if it "
                                 f"needs the user. Output tail:\n{tail}")}))


def session_end(payload: dict) -> None:
    fc.release_leases(session=payload.get("session_id") or None)


# ------------------------------------------------------------------ posttool
def posttool(payload: dict) -> int:
    """Validate one edited goal/directive file (no cross-checks). Returns the exit code."""
    fp = (payload.get("tool_input") or {}).get("file_path")
    if payload.get("tool_name") not in ("Write", "Edit", "MultiEdit") or not fp:
        return 0
    path = Path(fp)
    if path.suffix != ".md" or path.name in ("README.md", "TEMPLATE.md") or not path.is_file():
        return 0
    folder = path.parent
    if folder.name == "directives" and folder.parent.name == "docs":
        validate = fc.validate_directive
    elif folder.name == "goals" and folder.parent.name == "docs":
        validate = fc.validate_goal
    else:
        return 0
    errors = [i for i in validate(path.stem, path.read_text()) if i.level == "error"]
    if not errors:
        return 0
    print("\n".join(str(i) for i in errors), file=sys.stderr)
    return 2


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    try:
        if sys.argv[1] == "posttool":
            return posttool(payload)
        {"pretool": pretool, "stop": stop, "session-end": session_end}[sys.argv[1]](payload)
    except Exception as e:  # fail open, but say so
        print(f"friday hook error ({sys.argv[1:]}): {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
