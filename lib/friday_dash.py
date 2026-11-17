"""`friday dash`: the master's status server. Standard library only.

A threaded `http.server` bound to 127.0.0.1 and this node's tailnet IPv4 (`tailscale ip -4`)
only; never 0.0.0.0, `::` or any other address. The port is the registry's `[dash] port`
(default 8787). Routes:

  POST /api/report   a node pushes its `friday status --json` snapshot; accepted only from a tailnet
                     peer that `tailscale whois` maps to the registry node named in the report
                     (localhost: the master node only)
  GET  /api/state    the merged state, read-only
  GET  /api/health   liveness and what the server is bound to
  GET  /<file>       static files from dash/static/ (the UI, status-03); `/` is index.html
"""
from __future__ import annotations

import ipaddress
import json
import mimetypes
import os
import re
import signal
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

import friday_fleet as ff
import friday_status as fs

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = PLUGIN_ROOT / "dash" / "static"
LOCALHOST = "127.0.0.1"
TAILNET_V4 = ipaddress.ip_network("100.64.0.0/10")  # Tailscale's IPv4 range (CGNAT)
MAX_BODY = 1 << 20  # 1 MiB, the cap on a report body
REQUEST_TIMEOUT = 10  # seconds a connection may sit idle before it is dropped
SCHEMA = 1
STALE_AFTER = 90  # seconds without a report before a node is "stale"
MASTER_EVERY = 30  # seconds between the master's in-process snapshots
PRS_EVERY = 120  # seconds between `gh pr list` rounds
SAFE_NODE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")
WHOIS_TTL = 300  # seconds a `tailscale whois` answer is cached
TYPES = {".js": "text/javascript", ".mjs": "text/javascript", ".css": "text/css",
         ".html": "text/html", ".json": "application/json", ".svg": "image/svg+xml"}


class DashError(Exception):
    """friday dash cannot start (a refused bind address, a bad registry, a port in use)."""


def is_tailnet(ip: str) -> bool:
    try:
        return ipaddress.ip_address(ip) in TAILNET_V4
    except ValueError:
        return False


def tailnet_ipv4(run=subprocess.run) -> str | None:
    """This node's tailnet IPv4 from `tailscale ip -4`, or None when tailscale is missing, down,
    or prints something that is not a tailnet address."""
    try:
        r = run(["tailscale", "ip", "-4"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    lines = r.stdout.split()
    if not lines:
        return None
    ip = lines[0].strip()
    return ip if is_tailnet(ip) else None


def resolve_binds(requested, tailnet_ip: str | None) -> list[str]:
    """The addresses to listen on. With no `--bind`: 127.0.0.1 plus the tailnet address when there
    is one. Each `--bind` must be exactly one of those two; anything else (0.0.0.0, `::`, a
    hostname, a LAN address) raises DashError."""
    allowed = [LOCALHOST] + ([tailnet_ip] if tailnet_ip else [])
    if not requested:
        return allowed
    out: list[str] = []
    for raw in requested:
        addr = (raw or "").strip()
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            raise DashError(f"refusing --bind {raw!r}: not an IP address "
                            f"(friday dash binds only {' and '.join(allowed)})") from None
        if ip.is_unspecified:
            raise DashError(f"refusing --bind {raw!r}: friday dash never listens on all interfaces")
        norm = str(ip)
        if norm not in allowed:
            why = "" if tailnet_ip or not is_tailnet(norm) else " (tailscale reports no tailnet address)"
            raise DashError(f"refusing --bind {raw!r}: friday dash binds only "
                            f"{' and '.join(allowed)}{why}")
        if norm not in out:
            out.append(norm)
    return out


def master_url(reg) -> str:
    """http://<master host>:<[dash] port> from the registry's master node (its `tailnet` key, else the ssh host)."""
    if reg is None:
        raise DashError("no nodes file; pass --to <url>")
    m = next((n for n in reg.nodes.values() if n.role == "master"), None)
    if m is None:
        raise DashError("the registry has no master node; pass --to <url>")
    host = (m.tailnet or m.ssh.rpartition("@")[2]).strip()
    return f"http://{host}:{reg.dash_port}"


def push(snap: dict, url: str, timeout: float = 10) -> tuple[bool, str]:
    """POST one snapshot to <url>/api/report. (ok, message); never raises."""
    import urllib.error
    import urllib.request
    target = url.rstrip("/") + "/api/report"
    req = urllib.request.Request(target, data=json.dumps(snap).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return True, f"pushed {snap.get('node')} to {target} ({r.status})"
    except urllib.error.HTTPError as e:
        try:
            why = json.loads(e.read()).get("error", "")
        except (ValueError, OSError, AttributeError):
            why = ""
        return False, f"{target} answered {e.code}" + (f": {why}" if why else "")
    except (OSError, ValueError) as e:
        return False, f"cannot reach {target}: {e}"


def state_dir() -> Path:
    base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(base) / "friday" / "dash"


def repo_slug(origin) -> str | None:
    """`owner/repo` from a GitHub remote URL (https, ssh or scp form), else None."""
    if not isinstance(origin, str):
        return None
    m = re.search(r"github\.com[:/]+([^/\s]+)/([^/\s]+?)(?:\.git)?/?\Z", origin.strip())
    return f"{m.group(1)}/{m.group(2)}" if m else None


def load_registry(path=None):
    """(registry or None, port). No registry file: None and the default port."""
    reg_file = Path(path) if path else ff.find_nodes_file()
    if reg_file is None:
        return None, ff.DASH_PORT
    try:
        reg = ff.load_nodes(reg_file)
    except ff.RegistryError as e:
        raise DashError(str(e)) from e
    return reg, reg.dash_port


class Dash:
    """The server's state and route logic, separate from the HTTP plumbing so tests can drive it."""

    def __init__(self, registry=None, port: int = ff.DASH_PORT, binds=(), static_dir: Path = STATIC_DIR,
                 clock=time.time, run=subprocess.run, state_path: Path | None = None, collect=None):
        self.run = run
        self.collect = collect or fs.collect
        self.state_path = Path(state_path) if state_path is not None else state_dir()
        self.received: dict = {}  # node -> when the latest report arrived (server clock)
        self.prs: list = []
        self.prs_note: str | None = "open PRs not fetched yet"
        self.prs_time: float | None = None
        self._stop = threading.Event()
        self.whois_cache: dict = {}  # ip -> (expires, device name labels)
        self.reports: dict = {}  # node -> latest accepted snapshot (persisted in step 3)
        self.registry = registry
        self.port = port
        self.binds = list(binds)
        self.static_dir = Path(static_dir)
        self.clock = clock
        self.started = clock()
        self.lock = threading.Lock()
        self.load_saved()

    # ------------------------------------------------------------ persisted state
    def load_saved(self) -> None:
        """Reload the last report of each node from the state dir (a restart shows the last known
        state). Unreadable or malformed files are skipped."""
        try:
            files = sorted(self.state_path.glob("*.json"))
        except OSError:
            return
        for f in files:
            try:
                d = json.loads(f.read_text())
                snap, got = d["report"], float(d["received"])
                if f.stem != snap.get("node") or fs.check_schema(snap):
                    continue
            except (OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError):
                continue
            self.reports[f.stem] = snap
            self.received[f.stem] = got

    def _save(self, node: str, snap: dict, got: float) -> None:
        """Atomic write of ~/.local/state/friday/dash/<node>.json; failure is logged, not fatal."""
        if not SAFE_NODE.match(node):
            return
        tmp = self.state_path / f".{node}.json.tmp{os.getpid()}.{threading.get_ident()}"
        try:
            self.state_path.mkdir(parents=True, exist_ok=True)
            tmp.write_text(json.dumps({"received": got, "report": snap}))
            os.replace(tmp, self.state_path / f"{node}.json")
        except OSError as e:
            sys.stderr.write(f"friday dash: cannot save state for {node}: {e}\n")
            try:
                tmp.unlink()
            except OSError:
                pass

    def store(self, node: str, snap: dict) -> None:
        got = self.clock()
        with self.lock:
            self.reports[node] = snap
            self.received[node] = got
            self._save(node, snap, got)

    # ------------------------------------------------------------ master snapshot and PRs
    def master_name(self) -> str | None:
        if self.registry is None:
            return None
        return next((n.name for n in self.registry.nodes.values() if n.role == "master"), None)

    def refresh_master(self) -> bool:
        """Take the master's own snapshot in-process (no HTTP, no whois)."""
        name = self.master_name()
        if name is None:
            return False
        try:
            snap = self.collect(registry_path=self.registry.path, node_name=name)
            problems = fs.check_schema(snap)
            if problems or snap.get("node") != name:
                raise ValueError(problems[0] if problems else f"node is {snap.get('node')!r}")
        except Exception as e:
            sys.stderr.write(f"friday dash: master snapshot failed: {type(e).__name__}: {e}\n")
            return False
        self.store(name, snap)
        return True

    def refresh_prs(self) -> None:
        """Open `friday/*` PRs of every repo any node reported, via `gh pr list --json`. When gh is
        missing or fails everywhere, keep the old list and say why in prs_note."""
        with self.lock:
            slugs = sorted({s for r in self.reports.values() for repo in r.get("repos", [])
                            if (s := repo_slug(repo.get("origin")))})
        prs: list = []
        notes: list = []
        for slug in slugs:
            try:
                r = self.run(["gh", "pr", "list", "-R", slug, "--state", "open", "--limit", "100",
                              "--json", "number,title,url,headRefName,isDraft,author,updatedAt"],
                             capture_output=True, text=True, timeout=60)
            except FileNotFoundError:
                with self.lock:
                    self.prs_note = "gh is not installed; open PRs skipped"
                return
            except (OSError, subprocess.SubprocessError) as e:
                notes.append(f"{slug}: {type(e).__name__}")
                continue
            if r.returncode != 0:
                notes.append(f"{slug}: gh failed ({(r.stderr or '').strip()[:100] or r.returncode})")
                continue
            try:
                items = json.loads(r.stdout)
                for p in items:
                    if str(p.get("headRefName", "")).startswith("friday/"):
                        prs.append({"repo": slug, **p})
            except (ValueError, AttributeError, TypeError):
                notes.append(f"{slug}: unreadable gh output")
        with self.lock:
            if slugs and notes and len(notes) == len(slugs):
                self.prs_note = "gh unavailable: " + "; ".join(notes)
                return
            self.prs = prs
            self.prs_time = self.clock()
            self.prs_note = ("; ".join(notes) or None) if slugs else "no known repos yet"

    def start(self) -> None:
        """Background refresh: master snapshot every 30 s, PRs every 2 min."""
        def loop(fn, every):
            while True:
                try:
                    fn()
                except Exception as e:
                    sys.stderr.write(f"friday dash: {fn.__name__} failed: {type(e).__name__}: {e}\n")
                if self._stop.wait(every):
                    return
        for fn, every in ((self.refresh_master, MASTER_EVERY), (self.refresh_prs, PRS_EVERY)):
            threading.Thread(target=loop, args=(fn, every), name=f"dash-{fn.__name__}", daemon=True).start()

    def close(self) -> None:
        self._stop.set()

    def health(self) -> dict:
        now = self.clock()
        return {"ok": True, "schema": SCHEMA, "now": now, "started": self.started,
                "uptime_s": round(now - self.started, 1), "binds": self.binds, "port": self.port,
                "registry": str(self.registry.path) if self.registry else None,
                "nodes": len(self.registry.nodes) if self.registry else 0}

    def state(self) -> dict:
        now = self.clock()
        with self.lock:
            names = list(self.registry.nodes) if self.registry else []
            names += sorted(n for n in self.reports if n not in names)
            nodes = {}
            for n in names:
                got = self.received.get(n)
                if got is None:
                    nodes[n] = {"status": "missing", "last_seen": None, "age_s": None, "report": None}
                else:
                    age = max(0.0, now - got)
                    nodes[n] = {"status": "stale" if age > STALE_AFTER else "ok", "last_seen": got,
                                "age_s": round(age, 1), "report": self.reports[n]}
            return {"schema": SCHEMA, "generated": now, "stale_after_s": STALE_AFTER, "nodes": nodes,
                    "prs": list(self.prs), "prs_note": self.prs_note, "prs_time": self.prs_time}

    def whois_names(self, ip: str) -> set | None:
        """The lowercase names `tailscale whois --json <ip>` gives the device at that tailnet
        address (its short name and its full name), cached for WHOIS_TTL; None when unknown."""
        now = self.clock()
        with self.lock:
            hit = self.whois_cache.get(ip)
            if hit and hit[0] > now:
                return hit[1]
        names = None
        try:
            r = self.run(["tailscale", "whois", "--json", ip], capture_output=True, text=True, timeout=10)
            if r.returncode == 0:
                node = json.loads(r.stdout).get("Node")
                full = node.get("Name") if isinstance(node, dict) else None
                if isinstance(full, str) and full.strip(".").strip():
                    full = full.strip(".").lower()
                    names = {full, full.split(".")[0]}
        except (OSError, subprocess.SubprocessError, ValueError, AttributeError):
            names = None
        if names is not None:  # only answers are cached, so a node that just joined is not locked out
            with self.lock:
                self.whois_cache[ip] = (now + WHOIS_TTL, names)
        return names

    def node_for_device(self, names: set) -> str | None:
        """The registry node whose `tailnet` key (else the host of its `ssh`) names that device."""
        for n in self.registry.nodes.values():
            want = (n.tailnet or n.ssh.rpartition("@")[2]).strip(".").lower()
            if want and want in names:
                return n.name
        return None

    def report(self, peer_ip: str, headers, rfile) -> tuple[int, dict]:
        """Accept or refuse one pushed report: 403 for a sender that is not who it claims, 400 for
        a bad body. Every refusal logs one line; the body is read only after the sender passes."""
        def refuse(code: int, why: str):
            sys.stderr.write(f"friday dash: refused report from {peer_ip}: {why}\n")
            return code, {"error": why}

        if self.registry is None:
            return refuse(403, "no registry loaded")
        local = peer_ip == LOCALHOST
        if local:
            sender = next((n.name for n in self.registry.nodes.values() if n.role == "master"), None)
            if sender is None:
                return refuse(403, "localhost report but the registry has no master node")
        else:
            if not is_tailnet(peer_ip):
                return refuse(403, "peer is not a tailnet address")
            names = self.whois_names(peer_ip)
            if names is None:
                return refuse(403, "tailscale whois does not know this peer")
            sender = self.node_for_device(names)
            if sender is None:
                return refuse(403, f"device {sorted(names)[0]!r} is not a registry node")
        raw_len = headers.get("Content-Length")
        try:
            length = int(raw_len)
            if length < 0:
                raise ValueError
        except (TypeError, ValueError):
            return refuse(400, "missing or invalid Content-Length")
        if length > MAX_BODY:
            return refuse(400, f"body larger than {MAX_BODY} bytes")
        body = rfile.read(length)
        if len(body) != length:
            return refuse(400, "body shorter than Content-Length")
        try:
            snap = json.loads(body)
        except (ValueError, RecursionError):
            return refuse(400, "body is not valid JSON")
        if not isinstance(snap, dict):
            return refuse(400, "body is not a JSON object")
        problems = fs.check_schema(snap)
        if problems:
            return refuse(400, f"not a schema {SCHEMA} report: {problems[0]}")
        if snap.get("node") != sender:
            return refuse(403, f"report says node {snap.get('node')!r} but the sender is {sender!r}"
                               + (" (localhost)" if local else ""))
        self.store(sender, snap)
        sys.stderr.write(f"friday dash: accepted report from {sender} ({peer_ip})\n")
        return 200, {"ok": True, "node": sender}

    def static_file(self, url_path: str) -> Path | None:
        """The file under static_dir that url_path names, or None (missing, a directory, a dotfile,
        or anything that resolves outside static_dir, symlinks included)."""
        rel = unquote(url_path).lstrip("/") or "index.html"
        parts = rel.split("/")
        if any(p in ("", ".", "..") or p.startswith(".") or "\\" in p or "\0" in p for p in parts):
            return None
        try:
            root = self.static_dir.resolve(strict=True)
            f = (root / rel).resolve(strict=True)
        except (OSError, RuntimeError):
            return None
        if not f.is_relative_to(root) or not f.is_file():
            return None
        return f


class Handler(BaseHTTPRequestHandler):
    server_version = "friday-dash"
    sys_version = ""
    protocol_version = "HTTP/1.0"
    timeout = REQUEST_TIMEOUT

    @property
    def app(self) -> Dash:
        return self.server.app

    def log_message(self, fmt, *args) -> None:
        sys.stderr.write(f"friday dash: {self.client_address[0]} {fmt % args}\n")

    def _send(self, code: int, body: bytes, ctype: str, cache: str = "no-store") -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, code: int, obj) -> None:
        self._send(code, (json.dumps(obj) + "\n").encode(), "application/json")

    def _route(self, method: str) -> None:
        try:
            path = urlsplit(self.path).path
            if method == "POST":
                if path == "/api/report":
                    self.close_connection = True
                    code, obj = self.app.report(self.client_address[0], self.headers, self.rfile)
                    return self._json(code, obj)
                return self._json(404 if path.startswith("/api/") else 405, {"error": "not found"})
            if path == "/api/state":
                return self._json(200, self.app.state())
            if path == "/api/health":
                return self._json(200, self.app.health())
            if path.startswith("/api/"):
                return self._json(404, {"error": "not found"})
            f = self.app.static_file(path)
            if f is None:
                return self._send(404, b"not found\n", "text/plain; charset=utf-8")
            ctype = TYPES.get(f.suffix.lower()) or mimetypes.guess_type(f.name)[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype == "application/json":
                ctype += "; charset=utf-8"
            return self._send(200, f.read_bytes(), ctype, cache="no-cache")
        except Exception as e:  # one bad request must not take the server down or leak a traceback
            self.log_message("error %s: %s", type(e).__name__, e)
            try:
                self._json(500, {"error": "internal error"})
            except OSError:
                pass

    def do_GET(self) -> None:
        self._route("GET")

    def do_HEAD(self) -> None:
        self._route("GET")

    def do_POST(self) -> None:
        self._route("POST")


class DashServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, addr, app: Dash):
        if ipaddress.ip_address(addr[0]).is_unspecified:  # last line of defence behind resolve_binds
            raise DashError("friday dash never listens on all interfaces")
        self.app = app
        super().__init__(addr, Handler)


def serve(app: Dash, binds, port: int) -> list[DashServer]:
    """Bind every address (all or none) and start a serving thread for each."""
    servers: list[DashServer] = []
    try:
        for b in binds:
            servers.append(DashServer((b, port), app))
    except OSError as e:
        for s in servers:
            s.server_close()
        raise DashError(f"cannot listen on {b}:{port}: {e.strerror or e}") from e
    for s in servers:
        threading.Thread(target=s.serve_forever, name=f"dash-{s.server_address[0]}", daemon=True).start()
    return servers


def stop(servers) -> None:
    for s in servers:
        s.shutdown()
        s.server_close()


def main(binds_requested=None, registry_path=None) -> int:
    """`friday dash [--bind ADDR]...`: serve until interrupted."""
    try:
        reg, port = load_registry(registry_path)
        tip = tailnet_ipv4()
        binds = resolve_binds(binds_requested, tip)
        app = Dash(reg, port, binds)
        servers = serve(app, binds, port)
        app.start()
    except DashError as e:
        print(f"friday dash: {e}", file=sys.stderr)
        return 1
    if tip is None and not binds_requested:
        print("friday dash: no tailnet address (is tailscale up?); serving localhost only", file=sys.stderr)
    print("friday dash: serving " + " ".join(f"http://{b}:{port}/" for b in binds)
          + (f" (registry {reg.path})" if reg else " (no registry)"), flush=True)
    done = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: done.set())
    try:
        done.wait()
    except KeyboardInterrupt:
        pass
    app.close()
    stop(servers)
    return 0
