#!/usr/bin/env python3
"""friday's hooks: one script, one subcommand per event. Standard library only.

  pretool      PreToolUse on Bash: deny list, ./run enforcement, no commits on main, hardware gate
  stop         Stop: while a directive is active in this worktree, its Verify: must pass
  session-end  SessionEnd: release this session's hardware leases
  notification Notification: a friday session stopped on a prompt; record it for status and the dash
  waiting-clear PreToolUse/PostToolUse/UserPromptSubmit: the session moved on; drop that record
  posttool     PostToolUse on Bash: record session approval of a hardware resource; on Write|Edit|MultiEdit: a goal/directive file's own format errors go
               back to the model (stderr, exit 2); warnings and clean files are silent

Every decision is deterministic and explained in its reason, so the agent learns the fix from
the refusal. Malformed input fails open (no decision): a hook bug must never wedge a session.
The rules and where they came from: docs/workflow.md ("Hooks") and docs/migrating-from-v0.md.
"""
from __future__ import annotations

import json
import os
import re
import shutil
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
    text = "\n".join([cmd] + [m for g in re.findall(fc._SUBST, cmd) for m in g if m])
    for pat, reason in DENY:
        if re.search(pat, text):
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


def _session_approved(cfg: dict, resource: str) -> bool:
    return (cfg.get("hardware_approval") or {}).get(resource) == "session"


def record_session_approval(payload: dict) -> None:
    """PostToolUse on Bash: the command ran, so the user allowed it. For each `session` resource it
    matched whose lease this session holds, mark the lease approved (it ends with the lease)."""
    session = payload.get("session_id") or ""
    cmd = (payload.get("tool_input") or {}).get("command") or ""
    if not session or not cmd:
        return
    cfg = fc.load_config(fc.repo_root(Path(payload.get("cwd") or ".")))
    for resource, patterns in (cfg.get("hardware") or {}).items():
        if not _session_approved(cfg, resource) or not any(re.search(p, cmd) for p in patterns):
            continue
        holder = fc.lease_holder(resource)
        if holder and holder.get("session") == session and not holder.get("approved"):
            fc.take_lease(resource, session, holder.get("note", ""), approved=True)


def check_hardware(cmd: str, cfg: dict, session: str) -> tuple[str, str] | None:
    hw = cfg.get("hardware") or {}
    matched = [r for r, pats in hw.items() if any(re.search(p, cmd) for p in pats)]
    if not matched:
        return None
    holders = {r: fc.lease_holder(r) for r in matched}
    for resource in matched:                       # another session's lease wins, for every resource
        holder = holders[resource]
        if holder and holder.get("session") != session:
            age = int((time.time() - holder["time"]) / 60)
            return "deny", (f"Hardware `{resource}` is held by another session on {holder.get('host')} "
                            f"({age} min ago: {holder.get('note', '')}). Wait, or ask the user to run "
                            f"`friday release {resource}`.")
    if session and _one_simple_command(cmd) and all(
            holders[r] and holders[r].get("approved") and _session_approved(cfg, r) for r in matched):
        for resource in matched:
            fc.take_lease(resource, session, cmd, approved=True)   # refresh the TTL, keep the approval
        return "allow", f"{', '.join(matched)} approved for this session"
    for resource in matched:
        h = holders[resource]
        fc.take_lease(resource, session, cmd, approved=bool(h and h.get("approved")))
    resource = matched[0]
    reason = (f"Hardware `{resource}`: this command touches a physical device. Lease taken and "
              f"held for this session; this approval covers this command only.")
    if (cfg.get("hardware_approval") or {}).get(resource) == "session":
        reason += f" Approving it once approves `{resource}` for the rest of the session."
    return "ask", reason


def _one_simple_command(cmd: str) -> bool:
    """True when `cmd` is a single simple command: no chaining, pipes, backgrounding, newlines or
    substitutions anywhere (quoted or not; conservative)."""
    c = cmd.strip()
    if not c or any(x in c for x in ("&", ";", "|", "`", "$(", "<(", ">(", "\n", "\r")):
        return False
    return len(fc.split_commands(c)) == 1


def _unsafe_batch(cmd: str) -> bool:
    """True when `cmd` holds text the pattern check cannot see: command or process substitution or a
    heredoc anywhere (quoted or not; conservative), or an unquoted `&` that backgrounds (`&&`, `>&`,
    `&>` and `2>&1` are not backgrounding)."""
    if any(x in cmd for x in ("`", "$(", "<(", ">(", "<<")):
        return True
    quote, i = None, 0
    while i < len(cmd):
        c = cmd[i]
        if quote:
            if c == "\\" and quote == '"':
                i += 1
            elif c == quote:
                quote = None
        elif c in "'\"":
            quote = c
        elif c == "\\":
            i += 1
        elif c == "&":
            if cmd.startswith("&&", i):
                i += 1
            elif not ((i > 0 and cmd[i - 1] in "<>") or cmd.startswith("&>", i)):
                return True
        i += 1
    return False


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
        if not marker or not root or not cmd.strip() or _unsafe_batch(cmd):
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
        simples = fc.split_commands(cmd)
        rxs = [(pat, ".*".join(re.escape(part) for part in pat.split("*")))
               for pat in parsed.get("allowed") or []]
        used: list[str] = []
        for simple in simples:
            hit = next((pat for pat, rx in rxs if re.fullmatch(rx, simple, re.S)), None)
            if hit is None:
                return None
            if hit not in used:
                used.append(hit)
        if simples:
            pats = ", ".join(f"`{p}`" for p in used)
            return "allow", f"pre-approved in {did} (on {base}): every command matches {pats}"
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
    waiting_clear(payload)
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


# ------------------------------------------------------------------ waiting on a prompt
def _waiting_identity(cwd: Path) -> tuple[str, str] | None:
    """(goal, directive) when `cwd` is a friday worktree (an active marker, or a dispatched
    session), else None. The goal comes from the directive, the friday/<goal> branch, or the
    tmux session name, in that order."""
    marker = fc.read_marker(cwd)
    if not marker and not os.environ.get("FRIDAY_DISPATCHED_FROM"):
        return None
    did = str((marker or {}).get("id") or "")
    goal = _goal_and_base(cwd, did)[0] if did else ""
    if not goal:
        br = fc.current_branch(cwd) or ""
        goal = br[len("friday/"):] if br.startswith("friday/") else ""
    if not goal:
        goal = _tmux_session().removeprefix("friday-")
    return (goal, did) if goal and fc.GOAL_RE.match(goal) else None


def _tmux_session() -> str:
    if not os.environ.get("TMUX"):
        return ""
    try:
        r = subprocess.run(["tmux", "display-message", "-p", "#S"], capture_output=True, text=True, timeout=5)
        return r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def notification(payload: dict) -> None:
    """Record that this session is waiting on the user, then push a fresh snapshot (detached,
    bounded: the session never waits on it). Idle and informational notices are not prompts."""
    kind = payload.get("notification_type") or ""
    if kind in ("idle_prompt", "auth_success", "auth_storage_failure", "elicitation_complete",
                "elicitation_response", "agent_completed", "plugin_notification") or kind.startswith("quota_"):
        return
    ident = _waiting_identity(Path(payload.get("cwd") or "."))
    if not ident:
        return
    goal, did = ident
    d = fc.waiting_dir()
    d.mkdir(parents=True, exist_ok=True)
    rec = {"goal": goal, "directive": did, "message": str(payload.get("message") or ""), "kind": kind,
           "tmux_session": _tmux_session() or f"friday-{goal}", "session_id": payload.get("session_id", ""),
           "time": time.time()}
    tmp = d / f".{goal}.json.tmp"
    tmp.write_text(json.dumps(rec))
    tmp.replace(d / f"{goal}.json")
    cmd = [sys.executable, str(Path(__file__).resolve().parent.parent / "bin" / "friday"), "status", "--push"]
    if shutil.which("timeout"):
        cmd = ["timeout", "30"] + cmd
    try:
        subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
    except OSError:
        pass


def waiting_clear(payload: dict) -> None:
    """The session moved on (a tool call, a prompt, a stop): remove its waiting record if any."""
    d = fc.waiting_dir()
    if not d.is_dir() or not any(d.glob("*.json")):
        return                                   # the common case costs one directory listing
    sid = payload.get("session_id") or ""
    for p in d.glob("*.json"):
        try:
            rec = json.loads(p.read_text())
        except (OSError, ValueError):
            continue
        if sid and rec.get("session_id") == sid:
            p.unlink(missing_ok=True)
    ident = _waiting_identity(Path(payload.get("cwd") or "."))
    if ident:
        (d / f"{ident[0]}.json").unlink(missing_ok=True)


# ------------------------------------------------------------------ posttool
def posttool(payload: dict) -> int:
    """Validate one edited goal/directive file (no cross-checks). Returns the exit code."""
    if payload.get("tool_name") == "Bash":
        record_session_approval(payload)
        return 0
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
        {"pretool": pretool, "stop": stop, "session-end": session_end,
         "notification": notification, "waiting-clear": waiting_clear}[sys.argv[1]](payload)
    except Exception as e:  # fail open, but say so
        print(f"friday hook error ({sys.argv[1:]}): {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
