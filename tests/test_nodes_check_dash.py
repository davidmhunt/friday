"""friday nodes --check adds a dash line per master/worker node from the dash's /api/state."""
import json
import os
import socket
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

FRIDAY = Path(__file__).resolve().parent.parent / "bin" / "friday"
FAKE_SSH = '#!/bin/bash\ncat >/dev/null\nexit 255\n'


def _state_server(state, port=0):
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps(state).encode()
            self.send_response(200 if self.path == "/api/state" else 404)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", port), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def _check(tmp_path, port):
    (tmp_path / "n.toml").write_text(f'''[dash]
port = {port}
[node.laptop]
role = "master"
ssh = "me@127.0.0.1"
repos = "~/r"
plugin_dir = "~/f"
[node.alfred]
role = "worker"
ssh = "me@alfred"
repos = "~/r"
plugin_dir = "~/f"
[node.pi]
role = "worker"
ssh = "me@pi"
repos = "~/r"
plugin_dir = "~/f"
''')
    ssh = tmp_path / "fakessh"
    ssh.write_text(FAKE_SSH)
    ssh.chmod(0o755)
    env = dict(os.environ, FRIDAY_NODES=str(tmp_path / "n.toml"), FRIDAY_SSH=str(ssh), HOME=str(tmp_path))
    return subprocess.run([sys.executable, str(FRIDAY), "nodes", "--check"], env=env,
                          capture_output=True, text=True, cwd=tmp_path)


def test_ok_stale_missing_lines(tmp_path):
    srv = _state_server({"nodes": {"laptop": {"status": "ok", "age_s": 12.4},
                                   "alfred": {"status": "stale", "age_s": 7200},
                                   "pi": {"status": "missing", "age_s": None}}})
    try:
        r = _check(tmp_path, srv.server_address[1])
    finally:
        srv.shutdown()
    out = r.stdout
    assert "dash: ok (12 s ago)" in out
    assert "dash: stale (last report 7200 s ago); fix: friday nodes --setup alfred" in out
    assert "dash: missing (never reported); fix: friday nodes --setup pi" in out
    assert "dash: not running" not in out


def test_not_running_is_one_line_and_other_checks_run(tmp_path):
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    r = _check(tmp_path, port)
    assert r.stdout.count("dash: not running; fix: friday dash up") == 1
    for name in ("laptop", "alfred", "pi"):
        assert name in r.stdout
    assert "unreachable" in r.stdout  # the ssh probes still ran


def test_missing_card_text_is_in_the_page_js():
    static = FRIDAY.parent.parent / "dash" / "static"
    js = "".join(p.read_text() for p in static.glob("*.js")) + "".join(p.read_text() for p in static.glob("*.mjs") if ".test." not in p.name)
    assert "never reported: run `friday nodes --setup " in js
    assert "` on the master" in js
