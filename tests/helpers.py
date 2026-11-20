"""Shared test helpers. A child process a test starts must never find a real docker, gh, ssh or claude."""
import sys
from pathlib import Path


def private_bin(directory):
    """Make `directory` (created if missing) a private bin directory: a `python3` and a `python` symlink
    to sys.executable and nothing else. Put it on a child PATH, after the test's fakes, in place of
    dirname(sys.executable) or any system directory (/usr/bin holds the real docker and gh). Returns it."""
    d = Path(directory)
    d.mkdir(parents=True, exist_ok=True)
    for name in ("python3", "python"):
        link = d / name
        if not link.is_symlink() and not link.exists():
            link.symlink_to(sys.executable)
    return d


SYSTEM_TOOLS = ("git", "python3", "bash", "sh", "cat", "grep", "sed", "mkdir", "mv", "cp", "rm", "ls", "dirname",
                "basename", "date", "env", "tr", "head", "cut", "readlink", "mktemp", "chmod", "id", "uname", "wc",
                "sort", "tail", "awk", "test", "true", "false", "ln", "touch", "sleep", "tee", "find", "xargs")


def tool_bin(directory):
    """A private bin directory of symlinks to the basic system tools (never docker, gh, ssh, claude or uv),
    for a child that runs a probe script locally. Returns it as a str for a PATH."""
    import shutil
    d = Path(directory)
    d.mkdir(parents=True, exist_ok=True)
    for t in SYSTEM_TOOLS:
        w = shutil.which(t)
        if w and not (d / t).is_symlink():
            (d / t).symlink_to(w)
    return str(d)

