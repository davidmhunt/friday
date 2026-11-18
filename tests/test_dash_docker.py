"""dash-01 step 4: the compose file, `friday dash up|down` against a fake docker and gh, --no-self.
Run: uv run --with pytest pytest -q tests/test_dash_docker.py"""
import io
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib"))
import friday_dash as fd  # noqa: E402
import friday_fleet as ff  # noqa: E402
import friday_status as fs  # noqa: E402

COMPOSE = ROOT / "deploy" / "compose.yaml"
FRIDAY = ROOT / "bin" / "friday"
TOKEN = "ghp_SECRET0123456789abcdef"

REG = """
[dash]
port = 8787
[node.laptop]
role = "master"
ssh = "me@127.0.0.1"
tailnet = "laptop-ts"
repos = "~/r"
plugin_dir = "~/f"
[node.alfred]
role = "worker"
ssh = "me@alfred-ts"
repos = "~/r"
plugin_dir = "~/f"
"""


# ---------------------------------------------------------------- compose.yaml
@pytest.fixture(scope="module")
def svc():
    doc = yaml.safe_load(COMPOSE.read_text())
    return doc, doc["services"]["friday-dash"]


def test_compose_host_network_and_restart(svc):
    _, s = svc
    assert s["network_mode"] == "host"
    assert s["restart"] == "unless-stopped"


def test_compose_mounts(svc):
    doc, s = svc
    vols = [v.split(":") for v in s["volumes"]]
    by_target = {v[1]: v for v in vols}
    reg = by_target["/home/friday/.config/friday/nodes.toml"]
    assert reg[0].endswith("/.config/friday/nodes.toml") and reg[2] == "ro"
    sock = by_target["/var/run/tailscale/tailscaled.sock"]
    assert sock[0] == "/var/run/tailscale/tailscaled.sock" and sock[2] == "ro"
    state = by_target["/home/friday/.local/state/friday/dash"]
    assert state[0] in doc["volumes"] and len(state) == 2  # a named volume, read-write


def test_compose_no_secret_values(svc):
    _, s = svc
    assert s["environment"] == ["GH_TOKEN"]  # passed through from the environment, no value
    text = COMPOSE.read_text()
    assert not re.search(r"(gh[pousr]_|github_pat_)\w+", text)
    assert not re.search(r"GH_TOKEN\s*[=:]\s*\S", re.sub(r"(?m)^\s*#.*$", "", text))


# ---------------------------------------------------------------- friday dash up / down
@pytest.fixture
def fakes(tmp_path):
    """A PATH holding only fake docker and gh (gh signed in unless signed_out is touched); each
    docker call records its argv and GH_TOKEN to docker.log."""
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    log = tmp_path / "docker.log"
    py = sys.executable
    (bin_ / "docker").write_text(f"""#!{py}
import json, os, sys
open({str(log)!r}, "a").write(json.dumps({{"argv": sys.argv[1:], "token": os.environ.get("GH_TOKEN")}}) + "\\n")
""")
    (bin_ / "gh").write_text(f"""#!{py}
import os, sys
if sys.argv[1:] == ["auth", "token"] and not os.path.exists({str(tmp_path / 'signed_out')!r}):
    print({TOKEN!r})
else:
    sys.exit(1)
""")
    for f in bin_.iterdir():
        f.chmod(f.stat().st_mode | stat.S_IXUSR)
    return tmp_path


def friday(fakes, *args, path=None):
    env = {k: v for k, v in os.environ.items() if k != "GH_TOKEN"}
    env["PATH"] = path if path is not None else f"{fakes / 'bin'}{os.pathsep}{os.path.dirname(sys.executable)}"
    env["HOME"] = str(fakes)
    return subprocess.run([sys.executable, str(FRIDAY), "dash", *args], env=env, capture_output=True, text=True)


def calls(fakes):
    return [json.loads(line) for line in (fakes / "docker.log").read_text().splitlines()]


def test_up_argv_and_token_in_env_only(fakes):
    r = friday(fakes, "up")
    assert r.returncode == 0, r.stderr
    (c,) = calls(fakes)
    assert c["argv"] == ["compose", "-f", str(COMPOSE), "up", "-d", "--build"]
    assert c["token"] == TOKEN
    assert TOKEN not in json.dumps(c["argv"])
    assert TOKEN not in r.stdout + r.stderr  # what it says it ran does not leak the token
    assert "docker compose -f" in r.stdout


def test_down_argv(fakes):
    r = friday(fakes, "down")
    assert r.returncode == 0, r.stderr
    (c,) = calls(fakes)
    assert c["argv"] == ["compose", "-f", str(COMPOSE), "down"]
    assert c["token"] is None


def test_up_with_gh_signed_out_leaves_token_unset(fakes):
    (fakes / "signed_out").write_text("")
    r = friday(fakes, "up")
    assert r.returncode == 0, r.stderr
    assert calls(fakes)[0]["token"] is None
    assert "GH_TOKEN left unset" in r.stdout


def test_up_without_docker_fails_clearly(fakes):
    (fakes / "bin" / "docker").unlink()
    r = friday(fakes, "up")
    assert r.returncode == 1
    assert "docker is not installed" in r.stderr
    assert not (fakes / "docker.log").exists()


# ---------------------------------------------------------------- --no-self and the localhost report
def make(tmp_path, collect, no_self):
    (tmp_path / "nodes.toml").write_text(REG)
    return fd.Dash(ff.load_nodes(tmp_path / "nodes.toml"), state_path=tmp_path / "state",
                   collect=collect, no_self=no_self, run=lambda *a, **k: subprocess.CompletedProcess(a, 1, "", ""))


def test_no_self_never_calls_collect(tmp_path, monkeypatch):
    called = []
    d = make(tmp_path, lambda **k: called.append(k), no_self=True)
    started = []
    monkeypatch.setattr(fd.threading.Thread, "start", lambda self: started.append(self.name))
    d.start()
    assert started == ["dash-refresh_prs"]  # the PR loop only
    assert called == []
    d.close()


def test_default_still_collects_master(tmp_path, monkeypatch):
    d = make(tmp_path, lambda **k: None, no_self=False)
    started = []
    monkeypatch.setattr(fd.threading.Thread, "start", lambda self: started.append(self.name))
    d.start()
    assert sorted(started) == ["dash-refresh_master", "dash-refresh_prs"]
    d.close()


def test_localhost_report_lands_as_master_with_no_self(tmp_path):
    called = []
    d = make(tmp_path, lambda **k: called.append(k), no_self=True)
    raw = json.dumps(fs.empty_snapshot("laptop", "laptop-host", 1.0)).encode()
    code, body = d.report("127.0.0.1", {"Content-Length": str(len(raw))}, io.BytesIO(raw))
    assert code == 200 and body["node"] == "laptop"
    assert d.state()["nodes"]["laptop"]["status"] == "ok"
    assert called == []
