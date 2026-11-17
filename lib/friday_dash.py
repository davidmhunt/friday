"""`friday dash`: the master's status server. Standard library only.

A threaded `http.server` bound to 127.0.0.1 and this node's tailnet IPv4 (`tailscale ip -4`)
only; never 0.0.0.0, `::` or any other address. The port is the registry's `[dash] port`
(default 8787). Routes:

  POST /api/report   a node pushes its `friday status --json` snapshot (sender check: status-02 step 2;
                     until it exists every report is refused with 403)
  GET  /api/state    the merged state, read-only
  GET  /api/health   liveness and what the server is bound to
  GET  /<file>       static files from dash/static/ (the UI, status-03); `/` is index.html
"""
from __future__ import annotations

import ipaddress
import json
import mimetypes
import signal
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

import friday_fleet as ff

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = PLUGIN_ROOT / "dash" / "static"
LOCALHOST = "127.0.0.1"
TAILNET_V4 = ipaddress.ip_network("100.64.0.0/10")  # Tailscale's IPv4 range (CGNAT)
MAX_BODY = 1 << 20  # 1 MiB, the cap on a report body
REQUEST_TIMEOUT = 10  # seconds a connection may sit idle before it is dropped
SCHEMA = 1
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
                 clock=time.time):
        self.registry = registry
        self.port = port
        self.binds = list(binds)
        self.static_dir = Path(static_dir)
        self.clock = clock
        self.started = clock()
        self.lock = threading.Lock()

    def health(self) -> dict:
        now = self.clock()
        return {"ok": True, "schema": SCHEMA, "now": now, "started": self.started,
                "uptime_s": round(now - self.started, 1), "binds": self.binds, "port": self.port,
                "registry": str(self.registry.path) if self.registry else None,
                "nodes": len(self.registry.nodes) if self.registry else 0}

    def state(self) -> dict:
        with self.lock:
            return {"schema": SCHEMA, "generated": self.clock(), "nodes": {}, "prs": []}

    def report(self, peer_ip: str, headers, rfile) -> tuple[int, dict]:
        """Accept or refuse one pushed report. The sender check is status-02 step 2; until then
        this fails closed and never reads the body."""
        return 403, {"error": "reports are not accepted yet (no sender check)"}

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
    stop(servers)
    return 0
