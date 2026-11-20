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


def test_awaiting_review_branch_skips_land_goal():
    i = SRC.index("if (awaiting) {\n  // Awaiting")
    j = SRC.index("const goalCmd", i)
    block = SRC[i:j]
    assert "acceptLine" in block and "friday land --goal ${d.goal}" in block
    assert "runLand" not in block
    assert "friday accept ${id}" in SRC and "d.review" in SRC
    # the push (friday land <id>) happens before this branch
    assert SRC.index("const land = await runLand(landCmd") < i


def test_awaiting_review_reported_for_land_none_and_pr():
    none_i = SRC.index("if (landMode === 'none') {")
    none_block = SRC[none_i:SRC.index("const land = await", none_i)]
    assert "if (awaiting) return" in none_block and "acceptLine" in none_block
    pr_i = SRC.index("if (landMode === 'pr') {")
    pr_block = SRC[pr_i:SRC.index("// Land goal", pr_i)]
    assert "if (awaiting) return" in pr_block and "acceptLine" in pr_block


# ---- Verify prompt and the ran=false path (tt-08, #28)

def _verify_prompt():
    i = SRC.index("async function verifyLoop")
    m = re.search(r"\bagent\(\s*`", SRC[i:])
    return _template_at(i + m.end() - 1)[0]


def test_verify_prompt_is_one_foreground_call():
    p = _verify_prompt()
    assert "one plain foreground" in p
    assert "600000" in p
    assert "several minutes" not in SRC


def test_verify_schema_has_ran():
    i = SRC.index("const VERIFY = {")
    block = SRC[i:SRC.index("\n}\n", i)]
    assert "ran: { type: 'boolean'" in block and "not_run_reason" in block
    assert "'ran'" in block.split("required:")[1].split("]")[0]


def _run_verify_loop(results):
    """Run the real verifyLoop under node with scripted agent results; return (outcome, calls)."""
    import json
    import shutil
    import subprocess
    import pytest
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    i = SRC.index("const verifyLineOf")
    j = SRC.index("// ---------------------------------------------------------------- prepare")
    k = SRC.index("const MAX_FIX_ROUNDS")
    consts = SRC[k:SRC.index("\n", SRC.index("const MAX_SAME_FAILURE"))]
    js = f"""
const id = 'x-01', directive = 'x'
const STEP = {{}}, VERIFY = {{}}
{consts}
const rulesBlock = () => ''
const state = {{ verify: '', review: '' }}
const results = {json.dumps(results)}
const calls = []
async function agent(prompt, opts) {{
  calls.push(opts.agentType)
  if (opts.agentType === 'friday:implementer') return {{ status: 'done' }}
  return results.shift()
}}
{SRC[i:j]}
verifyLoop({{ verify: 'make test', rules: [] }}, 'initial').then(r => console.log(JSON.stringify({{ r, calls }})))
"""
    out = subprocess.run([node, "-e", js], capture_output=True, text=True, check=True).stdout
    data = json.loads(out)
    return data["r"], data["calls"]


def test_ran_false_blocks_without_fix_rounds():
    r, calls = _run_verify_loop([
        {"ran": False, "not_run_reason": "denied", "passed": False, "exit_code": -1, "signature": "", "tail": ""}])
    assert r["ok"] is False and r["why"].startswith("Verify not run")
    assert "denied" in r["why"]
    assert "friday:implementer" not in calls


def test_ran_false_timeout_says_raise_timeout():
    r, _ = _run_verify_loop([
        {"ran": False, "not_run_reason": "timed out", "passed": False, "exit_code": -1, "signature": "", "tail": ""}])
    assert "Verify not run" in r["why"] and "raise the timeout" in r["why"]


def test_failing_ran_true_still_gets_fix_rounds():
    fail = {"ran": True, "passed": False, "exit_code": 1, "signature": "FAILED a", "tail": "t"}
    ok = {"ran": True, "passed": True, "exit_code": 0, "signature": "", "tail": ""}
    r, calls = _run_verify_loop([fail, ok])
    assert r["ok"] is True
    assert calls == ["friday:runner", "friday:implementer", "friday:runner"]


def test_verify_prompt_asks_for_denial_text_verbatim():
    assert "not_run_reason set to the denial or error text verbatim" in _verify_prompt()


def test_ran_false_without_reason_names_the_missing_reason():
    r, _ = _run_verify_loop([
        {"ran": False, "not_run_reason": "", "passed": False, "exit_code": -1, "signature": "", "tail": ""}])
    assert r["ok"] is False
    assert "Verify not run: the Verify call returned no reason (check the hook output)" in r["why"]
    assert "no reason given" not in r["why"]


def test_both_review_prompts_explain_plan_lines():
    reviews = [p for p in _agent_prompts() if "friday commits ${id}" in p]
    assert len(reviews) == 2
    for p in reviews:
        assert "A \\`plan\\` line is a plan edit made after the directive started" in p
        assert "Verify, Rules or Allowed commands" in p
