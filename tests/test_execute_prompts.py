"""Every workflow prompt that runs a friday command must carry the ALONE instruction."""
import re
from pathlib import Path

SRC = (Path(__file__).resolve().parent.parent / "workflows" / "execute.js").read_text()
CMD = re.compile(r"friday (parse|start|finish|land)\b")


def _template_at(i):
    """Return the template literal starting at SRC[i] == '`' (nested ${} aware) and its end."""
    j, depth = i + 1, 0
    while True:
        c = SRC[j]
        if c == "\\":
            j += 2
            continue
        if depth == 0 and c == "`":
            return SRC[i + 1:j], j + 1
        if c == "$" and SRC[j + 1] == "{":
            depth += 1
            j += 2
            continue
        if depth and c == "}":
            depth -= 1
        elif depth and c == "`":  # nested template inside ${}
            _, j = _template_at(j)
            continue
        j += 1


def _agent_prompts():
    """Template literals passed as the prompt (first argument) of agent(...)."""
    out = []
    for m in re.finditer(r"\bagent\(\s*`", SRC):
        out.append(_template_at(m.end() - 1)[0])
    return out


def _alone():
    m = re.search(r"const ALONE = (['\"])(.*?)(?<!\\)\1\n", SRC, re.S)
    assert m, "execute.js must define const ALONE"
    return m.group(2).replace("\\'", "'")


def _runs_friday(text):
    # A prompt runs a friday command when it names one, or runs an interpolated command
    # (`Run exactly `${cmd}``) built from one.
    return bool(CMD.search(text)) or "Run exactly" in text


def test_agent_prompts_found():
    prompts = _agent_prompts()
    assert len([p for p in prompts if _runs_friday(p)]) >= 5


def test_every_friday_prompt_references_alone():
    for body in _agent_prompts():
        if _runs_friday(body):
            assert "${ALONE}" in body or _alone() in body, body[:100]


def test_alone_forbids_chaining():
    text = _alone()
    for tok in ("`cd`", "`&&`", "`;`", "`|`", "echo"):
        assert tok in text, tok
    assert re.search(r"Do not use", text)
    assert "allow rules" in text


def test_no_prompt_asks_for_an_echoed_exit_code():
    forbidden = re.compile(r"echo\s+\$\?|\$\?")
    for body in _agent_prompts():
        stripped = body.replace("${ALONE}", "")
        assert not forbidden.search(stripped), body[:100]
        assert not re.search(r"\becho\b", stripped), body[:100]
