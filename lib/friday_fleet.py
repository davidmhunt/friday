"""Node registry for friday's fleet dispatch. Standard library only.

Registry file (TOML), first existing of: $FRIDAY_NODES, <plugin root>/nodes.toml,
~/.config/friday/nodes.toml. Top-level `report_to` (optional), `[dash]` (optional `port` for
`friday dash`, default 8787) and `[node.<name>]` tables.
"""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
ROLES = ("master", "worker", "target")
RUNTIMES = ("container", "native")
LAUNCHERS = ("tmux",)
DASH_PORT = 8787


class RegistryError(ValueError):
    """The nodes file is missing, unparsable, or invalid."""


@dataclass
class Node:
    name: str
    role: str
    ssh: str
    runtime: str = "native"
    tags: list = field(default_factory=list)
    repos: str = ""
    plugin_dir: str = ""
    launcher: str = "tmux"
    tailnet: str = ""  # optional tailnet device name when it differs from the host in `ssh`


@dataclass
class Registry:
    path: Path
    report_to: str | None
    nodes: dict  # name -> Node, in file order
    dash_port: int = DASH_PORT


def find_nodes_file() -> Path | None:
    cands = []
    env = os.environ.get("FRIDAY_NODES")
    if env:
        cands.append(Path(env).expanduser())
    cands.append(PLUGIN_ROOT / "nodes.toml")
    cands.append(Path.home() / ".config" / "friday" / "nodes.toml")
    for c in cands:
        if c.is_file():
            return c
    return None


def _str(name: str, key: str, val) -> str:
    if not isinstance(val, str) or not val.strip():
        raise RegistryError(f"node '{name}': '{key}' must be a non-empty string")
    return val


def load_nodes(path) -> Registry:
    path = Path(path)
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except OSError as e:
        raise RegistryError(f"cannot read {path}: {e}") from e
    except tomllib.TOMLDecodeError as e:
        raise RegistryError(f"{path}: invalid TOML: {e}") from e

    report_to = data.get("report_to")
    if report_to is not None and not isinstance(report_to, str):
        raise RegistryError("'report_to' must be a string")
    dash = data.get("dash", {})
    if not isinstance(dash, dict):
        raise RegistryError("'dash' must be a table")
    dash_port = dash.get("port", DASH_PORT)
    if isinstance(dash_port, bool) or not isinstance(dash_port, int) or not 1 <= dash_port <= 65535:
        raise RegistryError(f"[dash] 'port' must be an integer 1-65535, not {dash_port!r}")
    table = data.get("node")
    if not isinstance(table, dict) or not table:
        raise RegistryError(f"{path}: no [node.<name>] tables")

    nodes: dict = {}
    seen_ssh: dict = {}
    for name, raw in table.items():
        if not isinstance(raw, dict):
            raise RegistryError(f"node '{name}': must be a table")
        if "ssh" not in raw:
            raise RegistryError(f"node '{name}': missing key 'ssh'")
        ssh = _str(name, "ssh", raw["ssh"])
        if ssh in seen_ssh:
            raise RegistryError(
                f"node '{name}': duplicate 'ssh' {ssh!r} (already used by '{seen_ssh[ssh]}')")
        seen_ssh[ssh] = name
        role = raw.get("role")
        if role not in ROLES:
            raise RegistryError(
                f"node '{name}': unknown 'role' {role!r} (expected one of {', '.join(ROLES)})")
        runtime = raw.get("runtime", "native")
        if runtime not in RUNTIMES:
            raise RegistryError(
                f"node '{name}': unknown 'runtime' {runtime!r} (expected one of {', '.join(RUNTIMES)})")
        launcher = raw.get("launcher", "tmux")
        if launcher not in LAUNCHERS:
            raise RegistryError(
                f"node '{name}': unknown 'launcher' {launcher!r} (expected one of {', '.join(LAUNCHERS)})")
        tags = raw.get("tags", [])
        if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
            raise RegistryError(f"node '{name}': 'tags' must be a list of strings")
        repos = raw.get("repos", "")
        plugin_dir = raw.get("plugin_dir", "")
        if role in ("master", "worker"):
            for key, val in (("repos", repos), ("plugin_dir", plugin_dir)):
                if not val:
                    raise RegistryError(f"node '{name}': {role} needs key '{key}'")
                _str(name, key, val)
        tailnet = raw.get("tailnet", "")
        if tailnet != "":
            _str(name, "tailnet", tailnet)
        nodes[name] = Node(name, role, ssh, runtime, list(tags), repos, plugin_dir, launcher, tailnet)
    return Registry(path, report_to, nodes, dash_port)


class RouteError(ValueError):
    """No node fits a directive's `Node:` line."""


def _lowest(cands: list, load: dict):
    # min() keeps the first of equal keys, so ties go to registry order.
    return min(cands, key=lambda n: load.get(n.name, 0))


def route(node_line: str, nodes, load: dict) -> tuple:
    """Pick the node for a `Node:` line. Returns (node_name, reason)."""
    nodes = getattr(nodes, "nodes", nodes)
    members = list(nodes.values())
    line = (node_line or "").strip()
    if line == "any":
        workers = [n for n in members if n.role == "worker"]
        if not workers:
            raise RouteError("Node: any - the registry has no worker node")
        n = _lowest(workers, load)
        return n.name, f"any: worker '{n.name}' has the lowest load ({load.get(n.name, 0)})"
    if line.startswith("tag:"):
        tag = line[4:].strip()
        if not tag:
            raise RouteError("Node: 'tag:' needs a tag name")
        runners = [n for n in members if n.role in ("worker", "master") and tag in n.tags]
        if runners:
            n = _lowest(runners, load)
            return n.name, f"tag:{tag}: {n.role} '{n.name}' has the lowest load ({load.get(n.name, 0)})"
        targets = [n for n in members if n.role == "target" and tag in n.tags]
        masters = [n for n in members if n.role == "master"]
        if targets and masters:
            m, t = masters[0], targets[0]
            return m.name, (f"tag:{tag}: only target '{t.name}' has it, so master '{m.name}' "
                            f"runs the directive and its runner drives '{t.name}' over SSH")
        if targets:
            raise RouteError(f"Node: {line} - only target '{targets[0].name}' has the tag "
                             "and the registry has no master to drive it")
        raise RouteError(f"Node: {line} - no node has tag '{tag}'")
    if line.startswith("host:"):
        name = line[5:].strip()
        if name not in nodes:
            raise RouteError(f"Node: {line} - no node named '{name}' in the registry")
        n = nodes[name]
        if n.role == "target":
            raise RouteError(f"Node: {line} - '{name}' is a target and cannot run directives; "
                             "use a tag: line so the master drives it over SSH")
        return name, f"host:{name}: named explicitly"
    raise RouteError(f"Node: {node_line!r} - expected 'any', 'tag:<x>' or 'host:<name>'")


PATH_PREAMBLE = 'export PATH="$HOME/.local/bin:$PATH"\n'


def ssh_cmd(node, script: str) -> tuple:
    """One remote call: returns (argv, stdin_text). The script is fed to `bash -s` on stdin.

    Non-interactive ssh on the workstation lacks ~/.local/bin (where claude and uv live), so
    every script starts with the PATH export.
    """
    argv = [os.environ.get("FRIDAY_SSH") or "ssh", "-o", "ConnectTimeout=5",
            "-o", "BatchMode=yes", node.ssh, "bash", "-s"]
    return argv, PATH_PREAMBLE + script


def candidates(line: str, nodes) -> list:
    """Names of the nodes (registry order) that satisfy one `Node:` line.

    Raises RouteError (the same message `route` gives) when none does.
    """
    nodes = getattr(nodes, "nodes", nodes)
    targets = {k: v for k, v in nodes.items() if v.role == "target"}
    out = []
    for name, n in nodes.items():
        if n.role == "target":
            continue
        try:
            got, _ = route(line, {name: n, **targets}, {})
        except RouteError:
            continue
        if got == name:
            out.append(name)
    if not out:
        route(line, nodes, {})  # raises the specific RouteError
        raise RouteError(f"Node: {line} - no node satisfies it")
    return out


def common_nodes(lines: dict, nodes) -> list:
    """Nodes that satisfy every `Node:` line in `lines` ({directive id: line}).

    Raises RouteError naming the directives that conflict when the intersection is empty.
    """
    sets = {}
    for did, line in lines.items():
        try:
            sets[did] = candidates(line, nodes)
        except RouteError as e:
            raise RouteError(f"{did}: {e}") from e
    names = list(getattr(nodes, "nodes", nodes))
    ok = [n for n in names if all(n in s for s in sets.values())]
    if not ok:
        detail = "; ".join(f"{d} wants '{lines[d]}' ({', '.join(s)})" for d, s in sets.items())
        raise RouteError("no node satisfies every remaining directive: " + detail)
    return ok


LOAD_SCRIPT = ("echo FRIDAY_REACH ok\n"
               "n=$(tmux list-sessions -F '#{session_name}' 2>/dev/null | grep -c '^friday-')\n"
               'echo "FRIDAY_LOAD ${n:-0}"\n')


def probe_load(node, timeout: int = 30):
    """Reach a node and count its `friday-*` tmux sessions. Returns the count, None if unreachable."""
    import subprocess
    argv, stdin = ssh_cmd(node, LOAD_SCRIPT)
    try:
        r = subprocess.run(argv, input=stdin, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None
    lines = r.stdout.splitlines()
    if r.returncode != 0 or "FRIDAY_REACH ok" not in lines:
        return None
    for l in lines:
        if l.startswith("FRIDAY_LOAD "):
            try:
                return int(l.split()[1])
            except ValueError:
                break
    return 0


# Exit codes of the remote prepare script (0 = ok); each refusal prints `FRIDAY_REFUSE <kind>: ...`.
PREPARE_EXIT = {"untrusted": 30, "session": 31, "origin": 32, "worktree": 33, "branch": 34,
                "plugin": 35, "git": 36}


def remote_path(p: str) -> str:
    """Shell-quote a node path, keeping a leading `~` expandable by the remote shell."""
    import shlex
    if p == "~":
        return '"$HOME"'
    if p.startswith("~/"):
        return '"$HOME"/' + shlex.quote(p[2:])
    return shlex.quote(p)


def worktree_path(node, repo_name: str, goal: str) -> str:
    """The worktree path as the node's shell will see it (still with a leading `~` if repos has one)."""
    return f"{node.repos.rstrip('/')}/{repo_name}.friday/{goal}"


def prepare_script(node, goal: str, repo_name: str, origin_url: str, base: str,
                   plugin_commit: str) -> str:
    """The one remote script that prepares `node` for a dispatch of `goal`.

    Refuses (exit code from PREPARE_EXIT, message `FRIDAY_REFUSE <kind>: ...`) if `repos` is
    untrusted in ~/.claude.json, a tmux session friday-<goal> exists, the existing clone's origin
    differs from `origin_url`, or the worktree path / local branch friday/<goal> already exists.
    Never touches an existing checkout's working tree or branch. On success prints
    `FRIDAY_TRUSTED <path>` (after recording trust for the worktree) and `FRIDAY_WORKTREE <abs path>`.
    """
    import shlex
    q = shlex.quote
    code = PREPARE_EXIT
    repos = remote_path(node.repos)
    plugin = remote_path(node.plugin_dir)
    branch = f"friday/{goal}"
    return f"""set -u
refuse() {{ echo "FRIDAY_REFUSE $1: $2"; exit "$3"; }}
REPOS={repos}
PLUGIN={plugin}
REPO_NAME={q(repo_name)}
ORIGIN={q(origin_url)}
GOAL={q(goal)}
BRANCH={q(branch)}
BASE={q(base)}
COMMIT={q(plugin_commit)}
mkdir -p "$REPOS" || refuse git "cannot create $REPOS" {code['git']}
REPOS=$(cd "$REPOS" && pwd -P)
CLONE="$REPOS/$REPO_NAME"
WT="$REPOS/$REPO_NAME.friday/$GOAL"
# trust: repos or a parent must be accepted in ~/.claude.json
python3 - "$REPOS" <<'PY' || refuse untrusted "$REPOS is not trusted in ~/.claude.json" {code['untrusted']}
import json, os, sys
p = os.path.realpath(sys.argv[1])
try:
    projects = json.load(open(os.path.expanduser("~/.claude.json"))).get("projects", {{}})
except (OSError, ValueError):
    sys.exit(1)
while True:
    if isinstance(projects.get(p), dict) and projects[p].get("hasTrustDialogAccepted"):
        sys.exit(0)
    if p == os.path.dirname(p):
        sys.exit(1)
    p = os.path.dirname(p)
PY
if tmux has-session -t "=friday-$GOAL" 2>/dev/null; then
  refuse session "tmux session friday-$GOAL already exists" {code['session']}
fi
# plugin: fetch and check out the master's commit, detached
git -C "$PLUGIN" fetch -q origin && git -C "$PLUGIN" checkout -q --detach "$COMMIT" \\
  || refuse plugin "cannot check out $COMMIT in $PLUGIN" {code['plugin']}
# repo: reuse a matching clone, else clone from the master's origin
norm() {{ u=${{1%/}}; echo "${{u%.git}}"; }}
if [ -e "$CLONE" ]; then
  have=$(git -C "$CLONE" remote get-url origin 2>/dev/null) \\
    || refuse origin "$CLONE has no origin remote (master origin: $ORIGIN)" {code['origin']}
  [ "$(norm "$have")" = "$(norm "$ORIGIN")" ] \\
    || refuse origin "origin mismatch at $CLONE: node has $have, master has $ORIGIN" {code['origin']}
else
  git clone -q "$ORIGIN" "$CLONE" || refuse git "clone of $ORIGIN failed" {code['git']}
fi
[ -e "$WT" ] && refuse worktree "worktree $WT already exists" {code['worktree']}
if git -C "$CLONE" show-ref --verify --quiet "refs/heads/$BRANCH"; then
  refuse branch "local branch $BRANCH already exists in $CLONE" {code['branch']}
fi
git -C "$CLONE" fetch -q origin || refuse git "fetch in $CLONE failed" {code['git']}
if git -C "$CLONE" show-ref --verify --quiet "refs/remotes/origin/$BRANCH"; then
  git -C "$CLONE" worktree add -q -b "$BRANCH" --track "$WT" "origin/$BRANCH" \\
    || refuse git "worktree add failed" {code['git']}
else
  git -C "$CLONE" worktree add -q --no-track -b "$BRANCH" "$WT" "origin/$BASE" \\
    || refuse git "worktree add from origin/$BASE failed" {code['git']}
fi
# trust the new worktree (repos was trusted above): add it to ~/.claude.json, atomically
python3 - "$WT" <<'PY' || refuse untrusted "cannot record trust for $WT in ~/.claude.json" {code['untrusted']}
import json, os, shutil, sys, tempfile
wt = os.path.realpath(sys.argv[1])
cfg = os.path.expanduser("~/.claude.json")
try:
    data = json.load(open(cfg))
    if not isinstance(data, dict):
        sys.exit(1)
    projects = data.setdefault("projects", {{}})
    if not isinstance(projects, dict):
        sys.exit(1)
    entry = projects.get(wt)
    if not isinstance(entry, dict):
        entry = projects[wt] = {{}}
    entry["hasTrustDialogAccepted"] = True
    bak = cfg + ".friday-bak"
    if not os.path.exists(bak):
        shutil.copy2(cfg, bak)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(cfg), prefix=".claude.json.friday-")
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, indent=2)
    shutil.copymode(cfg, tmp)
    os.replace(tmp, cfg)
except (OSError, ValueError):
    sys.exit(1)
print("FRIDAY_TRUSTED " + wt)
PY
echo "FRIDAY_WORKTREE $WT"
"""


def run_text(goal: str, directives: list) -> str:
    """The prompt the dispatched session starts with: the remaining directives, in order."""
    steps = "\n".join(f"{n}. /friday:execute {d}" for n, d in enumerate(directives, 1))
    return (f"Run the remaining directives of goal {goal}, in this order, each with the slash "
            f"command shown:\n{steps}\n"
            "Start the next only when the previous ended done. Stop at the first that blocks.")


def report_text(goal: str, report_to: str) -> str:
    """The system-prompt addition telling the session how to report back to the master."""
    return (f"When the directives of goal {goal} are finished or one has blocked, send session "
            f"{report_to} exactly one message with SendMessage, then stop. If the goal landed, the "
            f"message is `done {goal} PR <url>` (the URL from the goal landing). If a directive "
            f"blocked, it is `blocked {goal} <id>: <reason>`. Send no other message.")


def launch_line(node, goal: str, worktree: str, master_host: str, directives: list,
                report_to: str) -> str:
    """The one command that starts the worker session in tmux on `node`. Every value is quoted."""
    import shlex
    q = shlex.quote
    return " ".join([
        "tmux new -d -s", q(f"friday-{goal}"), "-c", q(worktree),
        "env", q(f"FRIDAY_RUNTIME={node.runtime}"), q(f"FRIDAY_DISPATCHED_FROM={master_host}"),
        "claude --model opus --permission-mode auto --remote-control",
        "--name", q(f"{goal}.{node.name}"), "--plugin-dir", remote_path(node.plugin_dir),
        "--append-system-prompt", q(report_text(goal, report_to)),
        q(run_text(goal, directives))])


def dispatches_path() -> Path:
    """`dispatches.jsonl` on the master, under XDG_STATE_HOME (default ~/.local/state)."""
    base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(base) / "friday" / "dispatches.jsonl"


def record_dispatch(rec: dict) -> Path:
    """Append one JSON line describing a dispatch. Master-side only; touches no goal or directive file."""
    import json
    p = dispatches_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as f:
        f.write(json.dumps(rec, sort_keys=True) + "\n")
    return p
