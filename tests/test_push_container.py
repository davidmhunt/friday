"""push = "container": setup/check against a fake ssh (runs the remote script locally), fake docker and fake systemctl."""
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from test_node_setup import _tools, FAKE

ROOT = Path(__file__).resolve().parent.parent
FRIDAY = ROOT / "bin" / "friday"
sys.path.insert(0, str(ROOT / "lib"))

REG = '''[node.laptop]
role = "master"
ssh = "me@laptop"
repos = "~/r"
plugin_dir = "~/f"
%s
'''
# fake docker: logs argv; `info` lists $DK_RUNTIMES; `image inspect` succeeds when $DK_IMAGE exists;
# `ps` prints $DK_PS; `compose` also records the env the compose file is interpolated with.
DOCKER = r'''#!/bin/bash
echo "$@" >> "$0.argv"
case "$1" in
  info) cat "$0.runtimes" 2>/dev/null; exit 0;;
  image) [ -e "$0.image" ]; exit $?;;
  build) touch "$0.image"; exit 0;;
  ps) cat "$0.ps" 2>/dev/null; exit 0;;
  compose) env | grep -E '^(FRIDAY_|UID=|GID=)' | sort > "$0.env"; exit 0;;
esac
exit 0
'''


def _setup_env(tmp_path, push, runtimes="runc", image=False, ps=""):
    home = tmp_path / "home"
    (home / "r").mkdir(parents=True, exist_ok=True)
    (home / ".claude").mkdir(exist_ok=True)
    if not (home / "f").exists():
        (home / "f").symlink_to(ROOT)
    (tmp_path / "n.toml").write_text(REG % (f'push = "{push}"' if push else ""))
    for name, body in (("fakessh", FAKE), ("fakedocker", DOCKER), ("fakectl", '#!/bin/bash\necho "$@" >> "$0.argv"\n')):
        p = tmp_path / name
        p.write_text(body)
        p.chmod(0o755)
    (tmp_path / "fakedocker.runtimes").write_text(f"Runtimes: {runtimes}\n")
    (tmp_path / "fakedocker.ps").write_text(ps)
    img = tmp_path / "fakedocker.image"
    img.unlink(missing_ok=True)
    if image:
        img.touch()
    return dict(os.environ, FRIDAY_NODES=str(tmp_path / "n.toml"), FRIDAY_SSH=str(tmp_path / "fakessh"), HOME=str(home),
                FRIDAY_SYSTEMCTL=str(tmp_path / "fakectl"), FRIDAY_DOCKER=str(tmp_path / "fakedocker"),
                PATH=_tools(tmp_path, gh="ok", claude="in", uv="fake"))


def _nodes(tmp_path, env, *args):
    return subprocess.run([sys.executable, str(FRIDAY), "nodes", *args], env=env, capture_output=True, text=True,
                          cwd=tmp_path, stdin=subprocess.DEVNULL)


def _units(tmp_path):
    u = tmp_path / "home" / ".config" / "systemd" / "user"
    u.mkdir(parents=True, exist_ok=True)
    for n in ("friday-push.timer", "friday-push.service"):
        (u / n).write_text("old\n")
    return u


def _argv(tmp_path, name):
    p = tmp_path / f"{name}.argv"
    return p.read_text().splitlines() if p.exists() else []


def test_setup_container_runs_compose_with_env_and_removes_timer(tmp_path):
    env = _setup_env(tmp_path, "container")
    u = _units(tmp_path)
    r = _nodes(tmp_path, env, "--setup", "laptop", "--yes")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "friday-push container running" in r.stdout
    compose = [l for l in _argv(tmp_path, "fakedocker") if l.startswith("compose")]
    assert len(compose) == 1
    assert compose[0] == f"compose -f {tmp_path}/home/f/deploy/push.compose.yaml up -d"
    e = dict(l.split("=", 1) for l in (tmp_path / "fakedocker.env").read_text().splitlines())
    assert e["FRIDAY_REPOS"] == str(tmp_path / "home" / "r")
    assert e["FRIDAY_LEASE_DIR"] == str(tmp_path / "home" / ".local/state/friday/leases")
    assert "FRIDAY_TMUX_DIR" not in e   # nothing tmux-related is created on the host
    assert e["UID"] == str(os.getuid()) and e["GID"] == str(os.getgid())
    assert not (u / "friday-push.timer").exists() and not (u / "friday-push.service").exists()
    assert "--user disable --now friday-push.timer" in _argv(tmp_path, "fakectl")
    # image was missing, so it was built; never pruned
    assert any(l.startswith("build -t friday-dash:local") for l in _argv(tmp_path, "fakedocker"))
    assert not any("prune" in l or l.startswith("rmi") for l in _argv(tmp_path, "fakedocker"))


def test_setup_container_skips_build_when_image_exists(tmp_path):
    env = _setup_env(tmp_path, "container", image=True)
    r = _nodes(tmp_path, env, "--setup", "laptop", "--yes")
    assert r.returncode == 0, r.stdout + r.stderr
    assert not any(l.startswith("build") for l in _argv(tmp_path, "fakedocker"))


def test_gpu_overlay_only_with_nvidia_runtime(tmp_path):
    env = _setup_env(tmp_path, "container", runtimes="io.containerd.runc.v2 nvidia runc", image=True)
    assert _nodes(tmp_path, env, "--setup", "laptop", "--yes").returncode == 0
    compose = [l for l in _argv(tmp_path, "fakedocker") if l.startswith("compose")][0]
    assert f"-f {tmp_path}/home/f/deploy/push.gpu.compose.yaml" in compose
    (tmp_path / "fakedocker.argv").unlink()
    env = _setup_env(tmp_path, "container", runtimes="io.containerd.runc.v2 runc", image=True)
    assert _nodes(tmp_path, env, "--setup", "laptop", "--yes").returncode == 0
    compose = [l for l in _argv(tmp_path, "fakedocker") if l.startswith("compose")][0]
    assert "push.gpu.compose.yaml" not in compose
    gpu = yaml.safe_load((ROOT / "deploy" / "push.gpu.compose.yaml").read_text())
    dev = gpu["services"]["friday-push"]["deploy"]["resources"]["reservations"]["devices"][0]
    assert dev["driver"] == "nvidia"
    assert "nvidia" not in (ROOT / "deploy" / "push.compose.yaml").read_text().replace("nvidia-", "")


def test_switching_back_to_timer_stops_container_and_installs_timer(tmp_path):
    env = _setup_env(tmp_path, "timer", ps="abc123\n")
    r = _nodes(tmp_path, env, "--setup", "laptop", "--yes")
    assert r.returncode == 0, r.stdout + r.stderr
    d = _argv(tmp_path, "fakedocker")
    assert "stop abc123" in d and "rm abc123" in d
    assert not any(l.startswith("compose") for l in d)
    assert "container stopped and removed" in r.stdout
    unit = tmp_path / "home" / ".config" / "systemd" / "user"
    assert (unit / "friday-push.timer").exists() and (unit / "friday-push.service").exists()
    assert "--user enable --now friday-push.timer" in _argv(tmp_path, "fakectl")


def test_default_push_is_timer(tmp_path):
    env = _setup_env(tmp_path, None)
    assert _nodes(tmp_path, env, "--setup", "laptop", "--yes").returncode == 0
    assert not any(l.startswith("compose") for l in _argv(tmp_path, "fakedocker"))
    assert (tmp_path / "home/.config/systemd/user/friday-push.timer").exists()


def test_check_reports_stopped_container_with_fix(tmp_path):
    env = _setup_env(tmp_path, "container", ps="")
    r = _nodes(tmp_path, env, "--check")
    assert "push container stopped" in r.stdout, r.stdout + r.stderr
    assert "the friday-push container is not running on laptop" in r.stdout
    assert "friday nodes --setup laptop" in r.stdout


def test_check_reports_running_container_without_fix(tmp_path):
    env = _setup_env(tmp_path, "container", ps="abc123\n")
    r = _nodes(tmp_path, env, "--check")
    assert "push container running" in r.stdout, r.stdout + r.stderr
    assert "container is not running" not in r.stdout


def test_check_reports_timer_mode(tmp_path):
    env = _setup_env(tmp_path, "timer")
    r = _nodes(tmp_path, env, "--check")
    assert "push timer" in r.stdout and "push container" not in r.stdout


def test_invalid_push_value_is_an_error(tmp_path):
    env = _setup_env(tmp_path, "cron")
    for args in (("--check",), ("--setup", "laptop", "--yes")):
        r = _nodes(tmp_path, env, *args)
        assert r.returncode != 0
        assert "unknown 'push' 'cron'" in r.stdout + r.stderr
    r = subprocess.run([str(ROOT / "bin" / "friday"), "check"], cwd=ROOT, env={**os.environ, **env},
                       capture_output=True, text=True)
    assert r.returncode == 1 and "unknown 'push' 'cron'" in r.stdout
    # the summary counts the registry error as an error and leaves the warning count alone
    clean = subprocess.run([str(ROOT / "bin" / "friday"), "check"], cwd=ROOT, capture_output=True, text=True,
                           env={k: v for k, v in {**os.environ, **env}.items() if k != "FRIDAY_NODES"})
    import re as _re
    e0, w0 = map(int, _re.search(r"(\d+) error\(s\), (\d+) warning\(s\)", clean.stdout).groups())
    e1, w1 = map(int, _re.search(r"(-?\d+) error\(s\), (-?\d+) warning\(s\)", r.stdout).groups())
    assert (e1, w1) == (e0 + 1, w0)
    from friday_fleet import load_nodes, RegistryError
    with pytest.raises(RegistryError, match="unknown 'push'"):
        load_nodes(tmp_path / "n.toml")


def test_compose_file_mounts_user_restart_command():
    c = yaml.safe_load((ROOT / "deploy" / "push.compose.yaml").read_text())["services"]["friday-push"]
    assert c["image"] == "friday-dash:local" and c["build"]["dockerfile"] == "deploy/Dockerfile"
    assert c["user"] == "${UID}:${GID}"
    assert c["restart"] == "unless-stopped" and c["network_mode"] == "host"
    assert c["command"] == ["friday", "status", "--push", "--every", "30"]
    vols = c["volumes"]
    # only plain string mounts; the tmux socket is reached through the host's /tmp, which exists after
    # every reboot, never through a bind of /tmp/tmux-<uid> (a missing source makes the start fail and
    # Docker does not retry a failed start)
    assert all(isinstance(v, str) for v in vols)
    assert "/tmp:/host/tmp:ro" in vols
    assert not any("tmux" in v for v in vols)
    assert "FRIDAY_TMUX_SOCKET=/host/tmp/tmux-${UID}/default" in c["environment"]
    repos = [v for v in vols if v.startswith("${FRIDAY_REPOS")]
    assert len(repos) == 1 and repos[0].endswith(":${FRIDAY_REPOS}:ro")
    assert any(v.endswith(":/home/friday/.config/friday:ro") and v.startswith("${HOME}/.config/friday") for v in vols)
    lease = [v for v in vols if v.startswith("${FRIDAY_LEASE_DIR")][0]
    assert not lease.endswith(":ro")
    assert "/proc:/host/proc:ro" in vols
    env = c["environment"]
    assert "FRIDAY_PROC_ROOT=/host/proc" in env and "FRIDAY_PUSH_MODE=container" in env
    assert any(e.startswith("FRIDAY_DISK_PATH=${FRIDAY_REPOS") for e in env)


def test_dockerfile_has_tmux_git_and_no_amd64_only_reference():
    df = (ROOT / "deploy" / "Dockerfile").read_text()
    code = "\n".join(l for l in df.splitlines() if not l.lstrip().startswith("#"))
    assert re.search(r"\btmux\b", code) and re.search(r"\bgit\b", code)
    assert not re.search(r"amd64|x86_64|x86-64", code, re.I)
    assert "dpkg --print-architecture" in code
