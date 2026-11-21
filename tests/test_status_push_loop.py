"""`friday status --push --every N` loops; fs.collect reads the host through FRIDAY_* overrides.
Run: uv run --with pytest --with pyyaml pytest -q tests/test_status_push_loop.py"""
import json
import os
import signal
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib"))
import friday_status as fs  # noqa: E402

FRIDAY = ROOT / "bin" / "friday"
ENV_KEYS = ("FRIDAY_PROC_ROOT", "FRIDAY_DISK_PATH", "FRIDAY_TMUX_SOCKET", "FRIDAY_LEASE_DIR",
            "FRIDAY_PUSH_MODE", "FRIDAY_NODES")


def _server(code=200):
    got = []

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            got.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            self.send_response(code)
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, got


def _env(tmp_path):
    env = {k: v for k, v in os.environ.items() if k not in ENV_KEYS}
    env.update(HOME=str(tmp_path), XDG_STATE_HOME=str(tmp_path / "st"))
    return env


def _start(tmp_path, url, every="5"):
    return subprocess.Popen([sys.executable, str(FRIDAY), "status", "--push", "--to", url, "--every", every],
                            env=_env(tmp_path), cwd=tmp_path, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True)


def _wait(cond, secs=20):
    end = time.time() + secs
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.1)
    return False


def test_loop_pushes_twice_and_stops_on_sigterm(tmp_path):
    srv, got = _server()
    p = _start(tmp_path, f"http://127.0.0.1:{srv.server_port}")
    try:
        assert _wait(lambda: len(got) >= 2), "expected two pushes"
        p.send_signal(signal.SIGTERM)
        assert p.wait(timeout=10) == 0
    finally:
        if p.poll() is None:
            p.kill()
        srv.shutdown()
    assert got[0]["schema"] == 1


def test_failing_push_keeps_looping(tmp_path):
    srv, got = _server(code=500)
    p = _start(tmp_path, f"http://127.0.0.1:{srv.server_port}")
    try:
        assert _wait(lambda: len(got) >= 2), "a failed push must not end the loop"
        assert p.poll() is None
        p.send_signal(signal.SIGINT)
        assert p.wait(timeout=10) == 0
        assert "friday:" in p.stderr.read()
    finally:
        if p.poll() is None:
            p.kill()
        srv.shutdown()


def test_unreachable_dash_keeps_looping(tmp_path):
    srv, _ = _server()
    port = srv.server_port
    srv.shutdown()
    srv.server_close()
    p = _start(tmp_path, f"http://127.0.0.1:{port}")
    try:
        time.sleep(1.5)
        assert p.poll() is None
        p.send_signal(signal.SIGTERM)
        assert p.wait(timeout=10) == 0
    finally:
        if p.poll() is None:
            p.kill()


def test_every_validation(tmp_path):
    for args, msg in ((["--every", "2", "--push"], "at least 5"), (["--every", "9"], "only goes with --push")):
        r = subprocess.run([sys.executable, str(FRIDAY), "status", *args], env=_env(tmp_path),
                           cwd=tmp_path, capture_output=True, text=True)
        assert r.returncode != 0 and msg in r.stderr


def test_push_without_every_is_one_shot(tmp_path):
    srv, got = _server()
    r = subprocess.run([sys.executable, str(FRIDAY), "status", "--push", "--to",
                        f"http://127.0.0.1:{srv.server_port}"], env=_env(tmp_path), cwd=tmp_path,
                       capture_output=True, text=True, timeout=30)
    srv.shutdown()
    assert r.returncode == 0 and len(got) == 1


# ---------------------------------------------------------------- collect overrides
@pytest.fixture
def clean(monkeypatch, tmp_path):
    for k in ENV_KEYS:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "st"))
    monkeypatch.setenv("PATH", str(tmp_path / "bin") + os.pathsep + os.environ["PATH"])
    (tmp_path / "bin").mkdir()
    return tmp_path


def _fake_proc(d: Path, up=1234.5):
    d.mkdir()
    (d / "uptime").write_text(f"{up} 0.0\n")
    (d / "loadavg").write_text("0.11 0.22 0.33 1/2 3\n")
    (d / "meminfo").write_text("MemTotal: 1000 kB\nMemAvailable: 400 kB\n")


def _fake_tmux(tmp_path: Path):
    log = tmp_path / "tmux.log"
    exe = tmp_path / "bin" / "tmux"
    exe.write_text(f'#!/bin/sh\necho "$@" >> {log}\nexit 1\n')
    exe.chmod(0o755)
    return log


def test_proc_root_override(clean, monkeypatch):
    _fake_proc(clean / "proc")
    monkeypatch.setenv("FRIDAY_PROC_ROOT", str(clean / "proc"))
    h = fs.collect(cwd=clean)["health"]
    assert h["uptime_s"] == 1234.5 and h["load"] == [0.11, 0.22, 0.33]
    assert h["mem"] == {"total": 1000 * 1024, "used": 600 * 1024}


def test_proc_root_default_is_proc(clean):
    snap = fs.collect(cwd=clean)
    if Path("/proc/uptime").exists():
        assert snap["health"]["uptime_s"] is not None and snap["health"]["uptime_s"] != 1234.5


def test_disk_path_override(clean, monkeypatch):
    import shutil
    seen = []
    real = shutil.disk_usage
    monkeypatch.setattr(fs.shutil, "disk_usage", lambda p: seen.append(str(p)) or real(p))
    fs.collect(cwd=clean)
    assert seen[-1] != "/"
    monkeypatch.setenv("FRIDAY_DISK_PATH", "/")
    fs.collect(cwd=clean)
    assert seen[-1] == "/"


def test_tmux_socket_override_logs_dash_S(clean, monkeypatch):
    log = _fake_tmux(clean)
    monkeypatch.setenv("FRIDAY_TMUX_SOCKET", "/run/host/tmux.sock")
    fs.collect(cwd=clean)
    lines = log.read_text().splitlines()
    assert lines and all(l.startswith("-S /run/host/tmux.sock ") for l in lines)


def test_tmux_default_has_no_socket_flag(clean):
    log = _fake_tmux(clean)
    fs.collect(cwd=clean)
    lines = log.read_text().splitlines()
    assert lines and all(l.startswith("list-panes") for l in lines)


def test_lease_dir_override(clean, monkeypatch):
    d = clean / "leases"
    d.mkdir()
    (d / "gpu0.json").write_text(json.dumps({"resource": "gpu0", "session": "s", "host": "h",
                                              "time": time.time(), "note": ""}))
    assert fs.collect(cwd=clean)["leases"] == []
    monkeypatch.setenv("FRIDAY_LEASE_DIR", str(d))
    assert [l["resource"] for l in fs.collect(cwd=clean)["leases"]] == ["gpu0"]


def test_push_mode(clean, monkeypatch):
    assert fs.collect(cwd=clean)["push_mode"] == "timer"
    monkeypatch.setenv("FRIDAY_PUSH_MODE", "container")
    snap = fs.collect(cwd=clean)
    assert snap["push_mode"] == "container"
