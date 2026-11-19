"""Node registry for friday's fleet dispatch. Standard library only.

Registry file (TOML), first existing of: $FRIDAY_NODES, <plugin root>/nodes.toml,
~/.config/friday/nodes.toml. Top-level `report_to` (optional), `[dash]` (optional `port` for
`friday dash`, default 8787) and `[node.<name>]` tables.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11: last-resort fallback; `friday install` sets up 3.12
    import tomli as tomllib

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


NODE_FILE = Path.home() / ".config" / "friday" / "node.toml"
NODE_KEYS = ("name", "repos", "dash")


def node_file_path() -> Path:
    env = os.environ.get("FRIDAY_NODE_FILE")
    return Path(env).expanduser() if env else NODE_FILE


def load_node_file(path=None):
    """Read this node's identity file: (name, repos, dash_url), or None when absent.

    Missing keys come back as "". A malformed file is a RegistryError naming it."""
    p = Path(path) if path else node_file_path()
    if not p.is_file():
        return None
    try:
        data = tomllib.loads(p.read_text())
    except OSError as e:
        raise RegistryError(f"cannot read {p}: {e}") from e
    except tomllib.TOMLDecodeError as e:
        raise RegistryError(f"{p}: invalid TOML: {e}") from e
    unknown = sorted(set(data) - set(NODE_KEYS))
    if unknown:
        raise RegistryError(f"{p}: unknown key(s) {', '.join(unknown)}; "
                            f"allowed: {', '.join(NODE_KEYS)}")
    out = []
    for key in NODE_KEYS:
        val = data.get(key, "")
        if not isinstance(val, str):
            raise RegistryError(f"{p}: '{key}' must be a string")
        out.append(val.strip())
    if not out[0]:
        raise RegistryError(f"{p}: missing key 'name'")
    return tuple(out)


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


_PLUGIN_PY = """
import json, os, subprocess
want = os.path.realpath(os.path.expanduser(os.environ["FRIDAY_P"]))
state, where = "none", ""
try:
    out = subprocess.run(["claude", "plugin", "list", "--json"], capture_output=True, text=True, timeout=30).stdout
    for p in json.loads(out):
        if str(p.get("id", "")).startswith("friday@"):
            where = str(p.get("readFromFolder") or p.get("installPath") or "")
            if not p.get("enabled"):
                state = "disabled"
            elif where and os.path.realpath(os.path.expanduser(where)) == want:
                state = "same"
            else:
                state = "other"
            break
except Exception:
    state, where = "unknown", ""
print("FRIDAY_PROBE install=" + state)
print("FRIDAY_PROBE install_dir=" + where)
"""


def plugin_install_lines(node) -> str:
    """Shell lines that print `FRIDAY_PROBE install=<none|disabled|same|other|unknown>` and
    `install_dir=<dir>`: whether `friday@` is installed and enabled for the user, and from which
    directory (`same` means the node's plugin_dir)."""
    import shlex
    return (f"if command -v python3 >/dev/null 2>&1; then FRIDAY_P={remote_path(node.plugin_dir)} "
            f"python3 -c {shlex.quote(_PLUGIN_PY)} 2>/dev/null; else echo 'FRIDAY_PROBE install=unknown'; fi")


def parse_plugin_install(text: str) -> tuple:
    """(state, dir) from probe output; state is `unknown` when the lines are missing."""
    got = dict(l[len("FRIDAY_PROBE "):].split("=", 1) for l in text.splitlines()
               if l.startswith("FRIDAY_PROBE ") and "=" in l)
    return got.get("install", "unknown"), got.get("install_dir", "")


def probe_plugin_install(node, timeout: int = 60) -> str:
    """Ask `node` whether friday is installed from its plugin_dir. Returns the state string;
    any failure is `unknown` (callers then keep `--plugin-dir`)."""
    import subprocess
    argv, stdin = ssh_cmd(node, plugin_install_lines(node) + "\n")
    try:
        r = subprocess.run(argv, input=stdin, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    return parse_plugin_install(r.stdout)[0] if r.returncode == 0 else "unknown"


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
            "Start the next only when the previous ended done or awaiting review. Stop at the first that blocks.")


def report_text(goal: str, report_to: str) -> str:
    """The system-prompt addition telling the session how to report back to the master."""
    return (f"When the directives of goal {goal} are finished or one has blocked, send session "
            f"{report_to} exactly one message with SendMessage. If the goal landed, the "
            f"message is `done {goal} PR <url>` (the URL from the goal landing); after sending it, "
            f"run `friday session-end --goal {goal}` and stop. If the last directive ended and some "
            f"directives ended `awaiting review` (the user must run `friday accept <id>` then "
            f"`friday land --goal {goal}`), the message is `review {goal} <ids> PR-pending` "
            f"(the awaiting ids, comma separated); after sending it, do not run session-end "
            f"and stay open. If a directive "
            f"blocked, it is `blocked {goal} <id>: <reason>`; after sending it, do not run "
            f"session-end and stay open. Send no other message.")


def launch_line(node, goal: str, worktree: str, master_host: str, directives: list,
                report_to: str, installed: str = "") -> str:
    """The one command that starts the worker session in tmux on `node`. Every value is quoted.

    `installed` is the probe state (see plugin_install_lines): `same` means friday is installed
    and enabled from the node's plugin_dir, so `--plugin-dir` is omitted (hooks and skills load once).
    """
    import shlex
    q = shlex.quote
    plugin_flag = [] if installed == "same" else ["--plugin-dir", remote_path(node.plugin_dir)]
    return " ".join([
        "tmux new -d -s", q(f"friday-{goal}"), "-c", q(worktree),
        "env", q(f"FRIDAY_RUNTIME={node.runtime}"), q(f"FRIDAY_DISPATCHED_FROM={master_host}"),
        "claude --model opus --permission-mode auto --remote-control",
        "--name", q(f"{goal}.{node.name}"), *plugin_flag,
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


IDLE_SH = r"""idle() {
  tail=$(tmux capture-pane -p -t "=friday-$1:" 2>/dev/null | grep -v '^[[:space:]]*$' | tail -n 10) || return 1
  [ -n "$tail" ] || return 1
  printf '%s\n' "$tail" | grep -qiE 'esc to interrupt|do you want to|do you trust|enter to confirm|press enter to continue|allow (this|once|always)' && return 1
  printf '%s\n' "$tail" | grep -qE '^[[:space:]│|]*[❯>]([[:space:]]|$)'
}"""


def resume_script(node, goal: str, repo_name: str) -> str:
    """Read-only remote script for `dispatch --resume`: inspects `<repos>/<repo>.friday/<goal>`.

    Prints `FRIDAY_RESUME_MISSING <path>` when there is no worktree, else
    `FRIDAY_RESUME branch=<b> goalstatus=<word|-> session=<0|1> idle=<0|1|-> path=<abs path>` and one
    `FRIDAY_DIRTY <porcelain line>` per uncommitted file (ignoring `runs/`), and one
    `FRIDAY_DIRECTIVE <id> <status>` per directive of the worktree's goal file, in order (the worktree's
    copy, not the master's). Nothing is changed.
    """
    import shlex
    wt = remote_path(worktree_path(node, repo_name, goal))
    g = shlex.quote(goal)
    return f"""set -u
wt={wt}
[ -e "$wt/.git" ] || {{ echo "FRIDAY_RESUME_MISSING $wt"; exit 0; }}
wt=$(cd "$wt" && pwd -P)
{IDLE_SH}
branch=$(git -C "$wt" symbolic-ref -q --short HEAD 2>/dev/null || echo "(detached)")
session=0; idl=-
if tmux has-session -t "=friday-"{g} 2>/dev/null; then
  session=1
  if idle {g}; then idl=1; else idl=0; fi
fi
gs=$(sed -n 's/^Status:[[:space:]]*//p' "$wt/docs/goals/"{g}".md" 2>/dev/null | head -n 1)
echo "FRIDAY_RESUME branch=$branch goalstatus=${{gs:--}} session=$session idle=$idl path=$wt"
awk '/^## /{{s=($0=="## Directives")}} s && /^[0-9]+\\.[ \t]/{{sub(/^[0-9]+\\.[ \t]+/,""); id=$1; sub(/:$/,"",id); print id}}' "$wt/docs/goals/"{g}".md" 2>/dev/null | while read -r id; do
  st=$(sed -n 's/^Status:[[:space:]]*//p' "$wt/docs/directives/$id.md" 2>/dev/null | head -n 1)
  echo "FRIDAY_DIRECTIVE $id ${{st:-?}}"
done
git -C "$wt" status --porcelain -- . ':(exclude)runs' 2>/dev/null | sed 's/^/FRIDAY_DIRTY /'
"""


def unblock_script(node, goal: str, repo_name: str, did: str) -> str:
    """Remote script for `dispatch --resume --unblock <did>`: in the worktree's own copy of the directive,
    run `friday unblock` there (blocked -> approved, one commit). Prints `FRIDAY_UNBLOCKED <id>`, or
    `FRIDAY_NOT_BLOCKED <id> <status>` and changes nothing."""
    import shlex
    wt = remote_path(worktree_path(node, repo_name, goal))
    f = shlex.quote(f"docs/directives/{did}.md")
    return f"""set -u
wt={wt}
f="$wt"/{f}
st=$(sed -n 's/^Status:[[:space:]]*//p' "$f" 2>/dev/null | head -n 1)
case "$st" in
  blocked:*) ;;
  *) echo "FRIDAY_NOT_BLOCKED {did} ${{st:-?}}"; exit 0 ;;
esac
cd "$wt" || exit 1
fr=$(command -v friday || true)
[ -n "$fr" ] || fr={remote_path(node.plugin_dir)}/bin/friday
"$fr" unblock {did} >&2 || {{ echo "FRIDAY_UNBLOCK_FAILED {did}"; exit 0; }}
echo "FRIDAY_UNBLOCKED {did}"
"""


def parse_resume(text: str) -> dict:
    """Parse `resume_script` output: {"missing": path|None, "branch", "goalstatus", "session", "idle",
    "path", "dirty": [porcelain lines], "directives": [(id, status)]}."""
    import re
    out = {"missing": None, "branch": None, "goalstatus": "-", "session": False, "idle": None,
           "path": None, "dirty": [], "directives": []}
    for line in text.splitlines():
        if line.startswith("FRIDAY_DIRECTIVE "):
            parts = line.split(" ", 2)
            out["directives"].append((parts[1], parts[2] if len(parts) > 2 else "?"))
        elif line.startswith("FRIDAY_RESUME_MISSING "):
            out["missing"] = line.split(" ", 1)[1]
        elif line.startswith("FRIDAY_DIRTY "):
            out["dirty"].append(line[len("FRIDAY_DIRTY "):])
        elif line.startswith("FRIDAY_RESUME "):
            m = re.match(r"FRIDAY_RESUME branch=(\S*) goalstatus=(\S*) session=([01]) idle=(\S*) path=(.*)$", line)
            if m:
                out.update(branch=m.group(1), goalstatus=m.group(2), session=m.group(3) == "1",
                           idle=None if m.group(4) == "-" else m.group(4) == "1", path=m.group(5))
    return out


def latest_dispatch(goal: str):
    """The newest `dispatches.jsonl` record for `goal` (any kind), or None."""
    import json
    p = dispatches_path()
    if not p.is_file():
        return None
    last = None
    for line in p.read_text().splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if isinstance(r, dict) and r.get("goal") == goal:
            last = r
    return last


def inventory_script(node) -> str:
    """The one remote script that inventories goal worktrees and stray clones under `node.repos`.

    Read-only. Prints one line per `<repos>/<repo>.friday/<goal>` worktree:
    `FRIDAY_WT repo=<r> goal=<g> branch=<b> head=<sha> tracked=<0|1> untracked=<0|1> session=<0|1>
    idle=<0|1|-> goalstatus=<word|-> path=<abs path>` (paths come last, they may hold spaces) and one
    `FRIDAY_STRAY folder=<name> origin=<repo name> path=<abs path>` per clone whose folder name
    differs from its origin repo name. `tracked`/`untracked` ignore `runs/`. `idle` is `-` without a
    session, else 1 when the pane's last lines show the input prompt and no busy or waiting text.
    """
    return f"""set -u
REPOS={remote_path(node.repos)}
[ -d "$REPOS" ] || {{ echo "FRIDAY_INV_EMPTY no $REPOS"; exit 0; }}
REPOS=$(cd "$REPOS" && pwd -P)
{IDLE_SH}
for wt in "$REPOS"/*.friday/*/; do
  wt=${{wt%/}}
  [ -e "$wt/.git" ] || continue
  goal=$(basename "$wt")
  repo=$(basename "$(dirname "$wt")"); repo=${{repo%.friday}}
  branch=$(git -C "$wt" symbolic-ref -q --short HEAD 2>/dev/null || echo "(detached)")
  head=$(git -C "$wt" rev-parse --short HEAD 2>/dev/null || echo "?")
  st=$(git -C "$wt" status --porcelain -- . ':(exclude)runs' 2>/dev/null)
  tracked=0; untracked=0
  printf '%s\\n' "$st" | grep -q '^[^?[:space:]]\\|^ [^?[:space:]]' && tracked=1
  printf '%s\\n' "$st" | grep -q '^??' && untracked=1
  session=0; idl=-
  if tmux has-session -t "=friday-$goal" 2>/dev/null; then
    session=1
    if idle "$goal"; then idl=1; else idl=0; fi
  fi
  gs=$(sed -n 's/^Status:[[:space:]]*//p' "$wt/docs/goals/$goal.md" 2>/dev/null | head -n 1)
  echo "FRIDAY_WT repo=$repo goal=$goal branch=$branch head=$head tracked=$tracked untracked=$untracked session=$session idle=$idl goalstatus=${{gs:--}} path=$wt"
done
for d in "$REPOS"/*/; do
  d=${{d%/}}
  case "$d" in *.friday) continue;; esac
  [ -e "$d/.git" ] || continue
  url=$(git -C "$d" remote get-url origin 2>/dev/null) || continue
  name=$(basename "${{url%/}}"); name=${{name%.git}}; name=${{name##*:}}
  [ "$name" = "$(basename "$d")" ] || echo "FRIDAY_STRAY folder=$(basename "$d") origin=$name path=$d"
done
"""


def parse_inventory(text: str) -> dict:
    """Parse `inventory_script` output into {"worktrees": [dict], "stray": [dict]}."""
    import re
    out = {"worktrees": [], "stray": []}
    for line in text.splitlines():
        for tag, key, fields in (
                ("FRIDAY_WT ", "worktrees", ("repo", "goal", "branch", "head", "tracked", "untracked",
                                             "session", "idle", "goalstatus", "path")),
                ("FRIDAY_STRAY ", "stray", ("folder", "origin", "path"))):
            if not line.startswith(tag):
                continue
            rest = line[len(tag):]
            rec = {}
            for f in fields[:-1]:
                m = re.match(rf"{f}=(\S*)\s*", rest)
                if not m:
                    break
                rec[f] = m.group(1)
                rest = rest[m.end():]
            else:
                if rest.startswith("path="):
                    rec["path"] = rest[5:]
                    for b in ("tracked", "untracked", "session"):
                        if b in rec:
                            rec[b] = rec[b] == "1"
                    if "idle" in rec:
                        rec["idle"] = None if rec["idle"] == "-" else rec["idle"] == "1"
                    out[key].append(rec)
    return out


def _slug(origin_url: str) -> str:
    """`owner/repo` from a git remote URL (ssh, scp-style or https), else ''."""
    u = (origin_url or "").strip().rstrip("/")
    if u.endswith(".git"):
        u = u[:-4]
    u = u.replace(":", "/") if "://" not in u else u.split("://", 1)[1].split("/", 1)[-1]
    parts = [p for p in u.split("/") if p]
    return "/".join(parts[-2:]) if len(parts) >= 2 else ""


def pr_merged(origin_url: str, goal: str, run=None):
    """True/False: does `gh pr list --state merged --head friday/<goal>` find a PR (squash merges
    break ancestry, so never `git branch --merged`). None when gh is missing or fails."""
    import subprocess
    run = run or subprocess.run
    slug = _slug(origin_url)
    cmd = ["gh", "pr", "list", "--state", "merged", "--head", f"friday/{goal}", "--json", "number"]
    if slug:
        cmd[3:3] = ["-R", slug]
    try:
        r = run(cmd, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    try:
        return bool(json.loads(r.stdout or "[]"))
    except ValueError:
        return None


def branch_on_origin(origin_url: str, goal: str, run=None):
    """True/False: does `friday/<goal>` exist on origin (`git ls-remote --heads`)? None on failure."""
    import subprocess
    run = run or subprocess.run
    try:
        r = run(["git", "ls-remote", "--heads", origin_url, f"friday/{goal}"],
                capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    return bool(r.stdout.strip())


def decide_clean(inv: dict, origin_urls: dict, run=None, have_gh=None) -> dict:
    """Decide on the master which inventoried worktrees to remove.

    `origin_urls` maps repo name -> origin URL (the master's). Finished = a merged PR for
    `friday/<goal>`, or (no gh, or no merged PR found) the branch is gone from origin and the goal
    file says `done`. Anything unfinished, dirty, or with a session that is not idle is kept with a
    one-line reason. Returns {"remove": [wt], "keep": [(wt, reason)], "notes": [str]}; each wt gets
    "why" on removal. Without gh only the branch-gone rule applies and a note says so.
    """
    import shutil
    if have_gh is None:
        have_gh = shutil.which("gh") is not None
    out = {"remove": [], "keep": [], "notes": []}
    if not have_gh:
        out["notes"].append("gh not available: using the branch-gone rule only "
                            "(branch gone from origin and goal file says done)")
    for wt in inv.get("worktrees", []):
        goal = wt["goal"]
        url = origin_urls.get(wt["repo"], "")
        if not url:
            out["keep"].append((wt, f"no origin known for repo {wt['repo']}"))
            continue
        merged = pr_merged(url, goal, run) if have_gh else None
        if have_gh and merged is None:
            out["notes"].append(f"gh failed for {wt['repo']}/{goal}: using the branch-gone rule")
        why = None
        if merged:
            why = "PR merged"
        else:
            on = branch_on_origin(url, goal, run)
            if on is None:
                out["keep"].append((wt, "cannot tell whether friday/%s is on origin" % goal))
                continue
            if on:
                out["keep"].append((wt, "unfinished: no merged PR, branch still on origin"
                                    if have_gh and merged is False else
                                    "unfinished: branch still on origin"))
                continue
            if wt.get("goalstatus") != "done":
                out["keep"].append((wt, "branch gone from origin but goal file is not done "
                                        f"(status {wt.get('goalstatus', '-')})"))
                continue
            why = "branch gone from origin, goal done"
        if wt.get("tracked") or wt.get("untracked"):
            out["keep"].append((wt, "dirty: uncommitted "
                                + ("tracked changes" if wt.get("tracked") else "untracked files")))
        elif wt.get("session") and not wt.get("idle"):
            out["keep"].append((wt, f"session friday-{goal} is not idle"))
        else:
            out["remove"].append({**wt, "why": why})
    return out


def clean_script(node, items: list, dry_run: bool = False) -> str:
    """The remote script that removes finished goal worktrees (`items`: dicts with `repo`, `goal`, `path`).

    Per item: refuse unless its `friday-<goal>` session is absent or idle, kill that session, `git
    worktree remove` (never --force, so a dirty tree stays), `git branch -D friday/<goal>` in the clone
    (`<path>/../../<repo>`), `git worktree prune`, and drop `projects[<path>]` from ~/.claude.json
    (temp file + rename, other keys kept). With `dry_run` it prints the plan and changes nothing.
    Prints `FRIDAY_CLEANED repo/goal`, `FRIDAY_KEPT repo/goal reason` or (dry run) `FRIDAY_WOULD ...`.
    """
    import shlex
    rows = "\n".join(f"{shlex.quote(i['repo'])} {shlex.quote(i['goal'])} {shlex.quote(i['path'])}"
                     for i in items)
    return f"""set -u
DRY={1 if dry_run else 0}
{IDLE_SH}
untrust() {{
python3 - "$1" <<'PY'
import json, os, sys, tempfile
wt = sys.argv[1]
cfg = os.path.expanduser("~/.claude.json")
try:
    data = json.load(open(cfg))
    projects = data.get("projects") if isinstance(data, dict) else None
    if not isinstance(projects, dict):
        sys.exit(0)
    keys = {{k for k in (wt, os.path.realpath(wt)) if k in projects}}
    if not keys:
        sys.exit(0)
    for k in keys:
        del projects[k]
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(cfg), prefix=".claude.json.friday-")
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, indent=2)
    os.chmod(tmp, os.stat(cfg).st_mode & 0o777)
    os.replace(tmp, cfg)
except (OSError, ValueError):
    sys.exit(1)
PY
}}
while read -r repo goal wt; do
  [ -n "$repo" ] || continue
  eval "repo=$repo goal=$goal wt=$wt"
  id="$repo/$goal"
  clone="$(dirname "$(dirname "$wt")")/$repo"
  has_session=0
  if tmux has-session -t "=friday-$goal" 2>/dev/null; then
    has_session=1
    if ! idle "$goal"; then echo "FRIDAY_KEPT $id session friday-$goal is not idle"; continue; fi
  fi
  if [ "$DRY" = 1 ]; then
    [ "$has_session" = 1 ] && echo "FRIDAY_WOULD $id: tmux kill-session -t '=friday-$goal'"
    echo "FRIDAY_WOULD $id: git worktree remove $wt"
    echo "FRIDAY_WOULD $id: git -C $clone branch -D friday/$goal"
    echo "FRIDAY_WOULD $id: git -C $clone worktree prune"
    echo "FRIDAY_WOULD $id: remove projects[$wt] from ~/.claude.json"
    continue
  fi
  [ -e "$wt" ] && {{
    err=$(git -C "$clone" worktree remove "$wt" 2>&1) || {{ echo "FRIDAY_KEPT $id worktree remove refused: $(printf '%s' "$err" | head -n 1)"; continue; }}
  }}
  [ "$has_session" = 1 ] && tmux kill-session -t "=friday-$goal" 2>/dev/null
  git -C "$clone" branch -D "friday/$goal" >/dev/null 2>&1
  git -C "$clone" worktree prune
  untrust "$wt" || echo "FRIDAY_KEPT $id could not remove the trust entry from ~/.claude.json"
  echo "FRIDAY_CLEANED $id"
done <<'FRIDAY_ROWS'
{rows}
FRIDAY_ROWS
"""


def run_clean(node, origin_urls: dict, dry_run: bool = False, run=None) -> dict:
    """Inventory `node`, decide on the master, run the clean script there. Never raises.

    Returns {"cleaned": [id], "kept": [str], "would": [str], "strays": [dict], "notes": [str],
    "error": str|None}. `kept` holds `<id>: reason` lines from the decision and from the node.
    """
    import subprocess
    run = run or subprocess.run
    res = {"cleaned": [], "kept": [], "would": [], "strays": [], "notes": [], "error": None}

    def ssh(script):
        argv, stdin = ssh_cmd(node, script)
        r = run(argv, input=stdin, capture_output=True, text=True, timeout=300)
        if r.returncode != 0:
            raise RuntimeError((r.stderr or r.stdout or "").strip().splitlines()[-1:] and
                               (r.stderr or r.stdout).strip().splitlines()[-1]
                               or f"ssh exited {r.returncode}")
        return r.stdout

    try:
        inv = parse_inventory(ssh(inventory_script(node)))
        res["strays"] = inv["stray"]
        plan = decide_clean(inv, origin_urls)
        res["notes"] = plan["notes"]
        res["kept"] = [f"{w['repo']}/{w['goal']}: {why}" for w, why in plan["keep"]]
        if plan["remove"]:
            out = ssh(clean_script(node, plan["remove"], dry_run))
            for line in out.splitlines():
                if line.startswith("FRIDAY_CLEANED "):
                    res["cleaned"].append(line.split(" ", 1)[1])
                elif line.startswith("FRIDAY_KEPT "):
                    _id, _, why = line[len("FRIDAY_KEPT "):].partition(" ")
                    res["kept"].append(f"{_id}: {why}")
                elif line.startswith("FRIDAY_WOULD "):
                    res["would"].append(line[len("FRIDAY_WOULD "):])
    except (RuntimeError, OSError, subprocess.SubprocessError) as e:
        res["error"] = str(e) or type(e).__name__
    return res
