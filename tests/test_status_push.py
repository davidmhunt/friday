"""friday status --push posts the snapshot to the dash URL (explicit or from the registry)."""
import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

FRIDAY = Path(__file__).resolve().parent.parent / "bin" / "friday"


def _server(code=200):
    got = []

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            got.append((self.path, json.loads(self.rfile.read(int(self.headers["Content-Length"])))))
            self.send_response(code)
            self.end_headers()
            self.wfile.write(b'{"error": "nope"}' if code != 200 else b"{}")

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, got


def _push(tmp_path, *args, nodes=None):
    env = dict(os.environ, HOME=str(tmp_path), XDG_STATE_HOME=str(tmp_path / "st"))
    env.pop("FRIDAY_NODES", None)
    if nodes is not None:
        (tmp_path / "n.toml").write_text(nodes)
        env["FRIDAY_NODES"] = str(tmp_path / "n.toml")
    return subprocess.run([sys.executable, str(FRIDAY), "status", "--push", *args], env=env,
                          capture_output=True, text=True, cwd=tmp_path)


def test_push_to_explicit_url(tmp_path):
    srv, got = _server()
    r = _push(tmp_path, "--to", f"http://127.0.0.1:{srv.server_port}")
    srv.shutdown()
    assert r.returncode == 0, r.stderr
    assert got[0][0] == "/api/report" and got[0][1]["schema"] == 1


def test_push_url_from_registry_master(tmp_path):
    srv, got = _server()
    nodes = f'''[dash]
port = {srv.server_port}
[node.m]
role = "master"
ssh = "me@127.0.0.1"
repos = "~/r"
plugin_dir = "~/f"
[node.w]
role = "worker"
ssh = "me@elsewhere"
repos = "~/r"
plugin_dir = "~/f"
'''
    r = _push(tmp_path, nodes=nodes)
    srv.shutdown()
    assert r.returncode == 0, r.stderr
    assert len(got) == 1 and got[0][0] == "/api/report"


def test_push_refused_and_unreachable_exit_1(tmp_path):
    srv, got = _server(403)
    r = _push(tmp_path, "--to", f"http://127.0.0.1:{srv.server_port}")
    srv.shutdown()
    assert r.returncode == 1 and "403" in r.stderr and "nope" in r.stderr
    r = _push(tmp_path, "--to", "http://127.0.0.1:1")
    assert r.returncode == 1 and "cannot reach" in r.stderr


def test_push_without_registry_or_url(tmp_path):
    r = _push(tmp_path)
    assert r.returncode == 1 and "--to" in r.stderr
