#!/usr/bin/env python3
"""friday's hooks: one script, one subcommand per event. Standard library only.

  pretool      PreToolUse on Bash: deny list, ./run enforcement, no commits on main, hardware gate
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


_SHELLISH = {"ssh", "bash", "sh", "zsh", "dash", "eval", "xargs", "docker", "podman", "run", "watch", "env"}


def _runs_accept(cmd: str, depth: int = 0) -> bool:
    """True when some simple command in `cmd` invokes `friday accept`: directly, through
    `python3 .../bin/friday`, `uv run`, or as an argument string (ssh host '...', bash -c '...')."""
    for simple in fc.split_commands(cmd):
        argv = fc.argv_of(simple)
        for i, a in enumerate(argv):
            if Path(a).name in ("friday", "friday.py"):
                nxt = [x for x in argv[i + 1:] if not x.startswith("-")]
                if nxt and nxt[0] == "accept":
                    return True
            if (depth < 4 and i and re.search(r"\s", a)
                    and any(Path(x).name in _SHELLISH for x in argv[:i]) and _runs_accept(a, depth + 1)):
                return True
    return False


def check_accept(cmd: str) -> str | None:
    if _runs_accept(cmd):
        return ("`friday accept` is not allowed from an agent session: only the user accepts a directive "
                "that is awaiting review. Print the review bullets and the command, and stop.")
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


def _goal_and_base(cwd: Path, did: str) -> tuple[str, str]:
    """The directive's goal id and that goal's Base branch ('' when unreadable)."""
    root = fc.repo_root(cwd)
    if not root:
        return "", ""
    try:
        m = re.search(r"(?m)^Goal:\s*(\S+)\s*$", fc.directive_path(root, did).read_text())
        goal = m.group(1) if m else ""
        base = fc.parse_goal(fc.goal_path(root, goal).read_text())["base"] if goal else ""
    except OSError:
        return "", ""
    return goal, base.strip()


def check_commit(cmd: str, cwd: Path) -> tuple[str, str] | None:
    """A commit never lands on main/master during a directive. The repository judged is the one the
    command commits in (`cd DIR && git commit`, `git -C DIR commit`), not the session's cwd. The
    `Directive:` trailer is enforced by the commit-msg git hook for every committer."""
    here = cwd
    for simple in fc.split_commands(cmd):
        argv = fc.argv_of(simple)
        if not argv:
            continue
        if argv[0] == "cd":
            if len(argv) > 1 and argv[1] != "-":
                here = here / Path(argv[1]).expanduser()
            continue
        if len(argv) < 2 or argv[0] != "git":
            continue
        rest, target = argv[1:], here
        while rest and rest[0] in ("-C", "-c") and len(rest) > 1:   # git -C dir commit ...
            if rest[0] == "-C":
                target = target / Path(rest[1]).expanduser()
            rest = rest[2:]
        if not rest or rest[0] != "commit":
            continue
        marker = fc.read_marker(target)
        branch = fc.current_branch(target)
        if marker:
            goal, base = _goal_and_base(target, marker["id"])
            if branch in ("main", "master") or (base and branch == base):
                dest = f"friday/{goal}" if goal else f"friday/{marker['id']}"
                return "deny", f"Directive {marker['id']} commits go on the goal branch, not {branch}. Create or switch to {dest}."
        if branch in ("main", "master"):
            return "ask", f"Commit directly on {branch}?"
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


def _one_simple_command(cmd: str) -> bool:
    """True when `cmd` is a single simple command: no chaining, pipes, backgrounding, newlines or
    substitutions anywhere (quoted or not; conservative)."""
    c = cmd.strip()
    if not c or any(x in c for x in ("&", ";", "|", "`", "$(", "<(", ">(", "\n", "\r")):
        return False
    return len(fc.split_commands(c)) == 1


def _git_show(root: Path, spec: str) -> str | None:
    r = subprocess.run(["git", "show", spec], cwd=str(root), capture_output=True, text=True, timeout=20)
    return r.stdout if r.returncode == 0 else None


def check_preapproved(cmd: str, cwd: Path) -> tuple[str, str] | None:
    """A command matching `## Allowed commands` of the active directive, as committed on
    origin/<Base> (the plan the user approved), so a goal-branch edit cannot widen it. Base comes from
    the marker (outside the working tree) and is trusted only when it is not a friday/* branch and the
    goal file on origin/<Base> names the same Base. None (no decision) on any doubt."""
    try:
        marker = fc.read_marker(cwd)
        root = fc.repo_root(cwd)
        if not marker or not root or not _one_simple_command(cmd):
            return None
        did = marker["id"]
        base = str(marker.get("goal_base") or "").strip()
        if not base or base.startswith("friday/") or base.startswith("-"):
            return None
        text = _git_show(root, f"origin/{base}:docs/directives/{did}.md")
        if text is None:
            return None
        parsed = fc.parse_directive_full(text)
        goal = (parsed.get("goal") or "").strip()
        if not goal or not fc.GOAL_RE.match(goal) or base == f"friday/{goal}":
            return None
        gtext = _git_show(root, f"origin/{base}:docs/goals/{goal}.md")
        if gtext is None or str(fc.parse_goal(gtext).get("base") or "").strip() != base:
            return None
        c = cmd.strip()
        for pat in parsed.get("allowed") or []:
            rx = ".*".join(re.escape(part) for part in pat.split("*"))
            if re.fullmatch(rx, c, re.S):
                return "allow", f"pre-approved in {did} (on {base})"
    except (OSError, subprocess.SubprocessError, KeyError, ValueError):
        return None
    return None


_PUSH_VALUE_OPTS = {"--repo", "-o", "--push-option", "--receive-pack", "--exec", "--signed", "--recurse-submodules"}


def _push_targets(args: list[str], target: Path) -> list[str] | None:
    """Branch names a `git push` with these args (after `push`) updates; None when not knowable
    (--all, --mirror, an unreadable current branch or upstream)."""
    pos, i = [], 0
    while i < len(args):
        a = args[i]
        if a in ("--all", "--mirror", "--branches"):
            return None
        if a in _PUSH_VALUE_OPTS:
            i += 2
            continue
        if a == "--":
            pos += args[i + 1:]
            break
        if not a.startswith("-"):
            pos.append(a)
        i += 1
    cur = fc.current_branch(target)
    specs = pos[1:]
    if not specs:
        if len(pos) == 1:                       # `git push origin`: the current branch
            return [cur] if cur else None
        up = fc._git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"], target)
        if not up:
            return [cur] if cur else None
        return [up.split("/", 1)[1] if "/" in up else up]
    out = []
    for sp in specs:
        dst = sp.lstrip("+").rsplit(":", 1)[-1]
        if dst in ("", "HEAD", "@"):
            if not cur:
                return None
            dst = cur
        out.append(dst[len("refs/heads/"):] if dst.startswith("refs/heads/") else dst)
    return out


def check_push(cmd: str, cwd: Path) -> str | None:
    """While a directive is active, `git push` may update only the goal's own branch (friday/<id>
    for `Land: pr`). Judged in the repository the command pushes from (`cd DIR &&`, `git -C DIR`).
    This keeps origin/<Base> from being edited into a trusted source by the agent."""
    here = cwd
    for simple in fc.split_commands(cmd):
        argv = fc.argv_of(simple)
        if not argv:
            continue
        if argv[0] == "cd":
            if len(argv) > 1 and argv[1] != "-":
                here = here / Path(argv[1]).expanduser()
            continue
        if len(argv) < 2 or argv[0] != "git":
            continue
        rest, target = argv[1:], here
        while rest and rest[0] in ("-C", "-c") and len(rest) > 1:
            if rest[0] == "-C":
                target = target / Path(rest[1]).expanduser()
            rest = rest[2:]
        if not rest or rest[0] != "push":
            continue
        marker = fc.read_marker(target)
        if not marker:
            continue
        did = marker["id"]
        goal, _ = _goal_and_base(target, did)
        ok = {f"friday/{goal}"} if goal else set()
        try:
            root = fc.repo_root(target)
            land = fc.parse_directive_full(fc.directive_path(root, did).read_text()).get("land", "")
        except (OSError, AttributeError):
            land = ""
        if land.strip().lower() == "pr":
            ok = {f"friday/{did}"}
        dests = _push_targets(rest[1:], target)
        if dests is None or not dests or any(d not in ok for d in dests):
            return (f"While {did} is active, `git push` may only update {' or '.join(sorted(ok)) or 'the goal branch'}"
                    f" (got {', '.join(dests) if dests else 'an unjudgeable target'}). Push the goal branch explicitly: "
                    f"git push origin {sorted(ok)[0] if ok else '<goal branch>'}.")
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
    if (r := check_accept(cmd)):
        results.append(("deny", r))
    if (r := check_run_only(cmd, cfg)):
        results.append(("deny", r))
    if (r := check_push(cmd, cwd)):
        results.append(("deny", r))
    if (r := check_commit(cmd, cwd)):
        results.append(r)
    pre = None if any(d == "deny" for d, _ in results) else check_preapproved(cmd, cwd)
    if not any(d == "deny" for d, _ in results) and (r := check_hardware(cmd, cfg, payload.get("session_id", ""))):
        results.append(("allow", f"{pre[1]}. {r[1]}") if pre and r[0] == "ask" else r)
    if pre:
        results.append(pre)
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
