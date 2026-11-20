"""Suite-wide guard: no test may reach the real docker, gh, ssh or claude.

At import (before any test runs) a stub directory goes first on PATH. Each stub prints a refusal
and exits 97, and logs the call to $FRIDAY_TEST_STUB_LOG when that is set. A test's own fakes,
placed ahead of it on a child PATH, still win; a child PATH built without the inherited PATH uses
tests/helpers.py (private_bin, tool_bin), which never links these tools."""
import os
import tempfile
from pathlib import Path

GUARDED = ("docker", "gh", "ssh", "claude")
STUB_DIR = Path(tempfile.mkdtemp(prefix="friday-test-stubs-"))

for _tool in GUARDED:
    _p = STUB_DIR / _tool
    _p.write_text(
        "#!/bin/sh\n"
        f'[ -n "$FRIDAY_TEST_STUB_LOG" ] && echo "{_tool} $* :: $PYTEST_CURRENT_TEST" >> "$FRIDAY_TEST_STUB_LOG"\n'
        f'echo "test stub: the real {_tool} is not available to tests" >&2\n'
        "exit 97\n")
    _p.chmod(0o755)

os.environ["PATH"] = f"{STUB_DIR}{os.pathsep}{os.environ.get('PATH', '')}"
