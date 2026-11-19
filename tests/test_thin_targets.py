"""tt-02 (#23): friday check warns on Allowed commands that pre-approve any remote command or a
remote build; a warning does not fail the check."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_preapproved import DIRECTIVE, allowed_section, fc  # noqa: E402


def _issues(pat, did="core-01"):
    text = DIRECTIVE.format(allowed=allowed_section([pat]))
    return fc.validate_directive(did, text)


@pytest.mark.parametrize("pat", [
    "ssh rover *", "ssh -p 22 rover *", "ssh rover bash -c *", "ssh rover docker build *",
])
def test_warns(pat):
    iss = _issues(pat)
    warns = [i for i in iss if i.level == "warning" and "worker" in i.message]
    assert warns, iss
    assert not [i for i in iss if i.level == "error"]


@pytest.mark.parametrize("pat", [
    "ssh rover ./run ros2 topic list", "tools/probe.sh *", "ssh rover cat /etc/os-release",
])
def test_no_warning(pat):
    assert not [i for i in _issues(pat) if "worker" in i.message]
