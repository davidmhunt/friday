import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
import pytest

import friday_status as fs

KEY = "-----BEGIN RSA PRIVATE KEY-----\nMIIEabc\ndefGHI\n-----END RSA PRIVATE KEY-----"
CASES = {
    "sk": ("key sk-ant-api03-AbCdEf123456 here", "sk-ant"),
    "ghp": ("ghp_abcdefghijklmnop1234", "ghp_abc"),
    "gho": ("token gho_abcdefghijklmnop1234", "gho_abc"),
    "akia": ("id AKIAIOSFODNN7EXAMPLE ok", "AKIAIOSFODNN7"),
    "auth": ("Authorization: Bearer abc.def.ghi", "abc.def"),
    "auth2": ("authorization: xyz123secret", "xyz123"),
    "password": ("run --password=hunter2xyz now", "hunter2"),
    "token": ("curl 'u?token=s3cr3tvalue&x=1'", "s3cr3t"),
}


@pytest.mark.parametrize("name", CASES)
def test_each_pattern_redacts(name):
    text, secret = CASES[name]
    out = fs.redact(text)
    assert secret not in out and fs.REDACTED in out
    assert fs.make_snippet(text) == [out]


def test_key_block_multiline_and_unterminated():
    out = fs.redact("before\n" + KEY + "\nafter")
    assert "MIIE" not in out and "defGHI" not in out
    assert out.startswith("before") and out.endswith("after")
    cut = fs.redact("x\n-----BEGIN OPENSSH PRIVATE KEY-----\nAAAAB3Nza")
    assert "AAAAB3" not in cut


def test_every_pattern_is_covered():
    # each REDACT_PATTERNS entry fires on at least one case above
    texts = [t for t, _ in CASES.values()] + [KEY]
    for name, rx in fs.REDACT_PATTERNS:
        assert any(rx.search(t) for t in texts), name


def test_plain_text_untouched():
    assert fs.redact("tokens used: 12, password prompt shown") == "tokens used: 12, password prompt shown"


def test_snippet_last_12_nonblank_cut_200():
    pane = "\n".join(f"line {i}\n" for i in range(30)) + "x" * 500 + "\n   \n"
    snip = fs.make_snippet(pane)
    assert len(snip) == 12 and snip[-1] == "x" * 200
    assert snip[0] == "line 19"


def test_cut_never_exposes_secret_prefix():
    line = "a" * 195 + " sk-abcdefghijklmnop"
    assert "sk-" not in fs.make_snippet(line)[0]


def test_session_state_snippet_and_waiting_line_redacted():
    pane = "Run a dynamic workflow? token=abcd1234efgh\n"
    st = fs.session_state("friday-g", 1, None, pane, marker={})
    assert "abcd1234" not in st["waiting_line"]
    assert all("abcd1234" not in ln for ln in st["snippet"])
    assert not fs.check_schema({**fs.empty_snapshot("n", "h", 0), "sessions": [st]})
