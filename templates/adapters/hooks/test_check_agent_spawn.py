#!/usr/bin/env python3
import sys
from pathlib import Path

# Add .agents/hooks directory to sys.path
sys.path.insert(0, str(Path(__file__).parent))

import pytest
from check_agent_spawn import evaluate, get_base_role


def test_get_base_role():
    assert get_base_role("coder") == "coder"
    assert get_base_role("coder-heavy") == "coder"
    assert get_base_role("planner-heavy") == "planner"
    assert get_base_role("runner-judgment") == "runner"
    assert get_base_role("reviewer-heavy") == "reviewer"
    assert get_base_role("researcher-heavy") == "researcher"
    assert get_base_role("researcher-quick") == "researcher"
    assert get_base_role("author") == "author"
    assert get_base_role("utility_agent") == "utility_agent"


def test_valid_base_role_spawn():
    payload = {
        "toolCall": {
            "name": "invoke_subagent",
            "args": {
                "Subagents": [
                    {
                        "TypeName": "coder",
                        "Role": "coder(mid): implement feature X",
                        "Prompt": "Implement feature X",
                        "Model": "inherit",
                    }
                ]
            },
        }
    }
    result = evaluate(payload)
    assert result["decision"] == "allow"
    assert "reason" not in result


def test_valid_heavy_variant_spawn():
    payload = {
        "toolCall": {
            "name": "invoke_subagent",
            "args": {
                "Subagents": [
                    {
                        "TypeName": "researcher-heavy",
                        "Role": "researcher-heavy(pro): prove convergence",
                        "Prompt": "[heavy] Prove convergence bounds",
                        "Model": "pro",
                    }
                ]
            },
        }
    }
    result = evaluate(payload)
    assert result["decision"] == "allow"
    assert "reason" not in result


def test_valid_quick_variant_spawn():
    payload = {
        "toolCall": {
            "name": "invoke_subagent",
            "args": {
                "Subagents": [
                    {
                        "TypeName": "researcher-quick",
                        "Role": "researcher-quick(inherit): look up bib entry",
                        "Prompt": "Check citation in references.bib",
                        "Model": "inherit",
                    }
                ]
            },
        }
    }
    result = evaluate(payload)
    assert result["decision"] == "allow"


def test_invalid_title_format_denied():
    payload = {
        "toolCall": {
            "name": "invoke_subagent",
            "args": {
                "Subagents": [
                    {
                        "TypeName": "researcher-heavy",
                        "Role": "bad title without model tag",
                        "Prompt": "[heavy] Prove convergence",
                        "Model": "pro",
                    }
                ]
            },
        }
    }
    result = evaluate(payload)
    assert result["decision"] == "deny"
    assert "required 'role(model): task' format" in result["reason"]


def test_heavy_prompt_without_escalation_soft_warning():
    payload = {
        "toolCall": {
            "name": "invoke_subagent",
            "args": {
                "Subagents": [
                    {
                        "TypeName": "researcher",
                        "Role": "researcher(inherit): prove convergence",
                        "Prompt": "[heavy] Prove convergence bounds",
                        "Model": "inherit",
                    }
                ]
            },
        }
    }
    result = evaluate(payload)
    assert result["decision"] == "allow"
    assert "SOFT WARNING" in result["reason"]
    assert "variant 'researcher-heavy'" in result["reason"]


def test_utility_spawn_exempt():
    payload = {
        "toolCall": {
            "name": "invoke_subagent",
            "args": {
                "Subagents": [
                    {
                        "TypeName": "search_helper",
                        "Role": "helper for searching",
                        "Prompt": "Search for xyz",
                        "Model": "flash",
                    }
                ]
            },
        }
    }
    result = evaluate(payload)
    assert result["decision"] == "allow"
    assert "reason" not in result


def test_antigravity_hooks_json_structure():
    """Verify hooks.json conforms to Antigravity's map[string]JSONHookSpec structure."""
    import json
    repo_root = Path(__file__).resolve().parents[4]
    for rel_path in (".agents/hooks.json", ".friday/templates/adapters/antigravity/hooks.json.tmpl"):
        hook_file = repo_root / rel_path
        if not hook_file.exists():
            continue
        data = json.loads(hook_file.read_text())
        assert isinstance(data, dict), f"{rel_path} must be a JSON object"
        # Must not have event names like PreToolUse at top level (must be wrapped under hook name)
        assert "PreToolUse" not in data, f"{rel_path} has PreToolUse at root; must be under a named hook key"
        assert "PostToolUse" not in data, f"{rel_path} has PostToolUse at root; must be under a named hook key"
        for hook_name, spec in data.items():
            assert isinstance(spec, dict), f"Hook spec {hook_name} in {rel_path} must be an object"
            for event_name in ("PreToolUse", "PostToolUse"):
                if event_name in spec:
                    assert isinstance(spec[event_name], list), f"{event_name} in {hook_name} must be a list"
                    for group in spec[event_name]:
                        assert "matcher" in group, f"Matcher group in {hook_name} missing 'matcher'"
                        assert "hooks" in group, f"Matcher group in {hook_name} missing 'hooks'"
                        assert isinstance(group["hooks"], list)



def _spawn_in_repo(tmp_path, type_name, title, prompt="do it"):
    """Run the hook as a subprocess with cwd = a consumer repo that registers
    a project role via `.friday-project/roles/widget.md` — discovery happens
    at import, so it must be a fresh interpreter."""
    import json
    import subprocess
    repo = tmp_path / "consumer"
    (repo / ".friday-project" / "roles").mkdir(parents=True)
    (repo / "harness.config.env").write_text("PROJECT_NAME=Test\n")
    (repo / ".friday-project" / "roles" / "widget.md").write_text("# Widget\n")
    (repo / ".friday-project" / "roles" / "coder.md").write_text("# collides\n")
    payload = {"toolCall": {"name": "Agent", "args": {
        "subagent_type": type_name, "description": title, "prompt": prompt}}}
    out = subprocess.run(
        [sys.executable, str(Path(__file__).parent / "check_agent_spawn.py")],
        cwd=repo, input=json.dumps(payload), capture_output=True, text=True,
    )
    return json.loads(out.stdout)


def test_project_role_is_registered_and_title_checked(tmp_path):
    assert _spawn_in_repo(tmp_path, "widget", "bad title")["decision"] == "deny"


def test_project_role_valid_title_allowed(tmp_path):
    res = _spawn_in_repo(tmp_path, "widget", "widget(mid): build the thing")
    assert res["decision"] == "allow"
    assert "reason" not in res


def test_project_role_heavy_without_escalation_warns(tmp_path):
    res = _spawn_in_repo(tmp_path, "widget", "widget(mid): x", prompt="[heavy] x")
    assert res["decision"] == "allow"
    assert "widget-heavy" in res.get("reason", "")


def _run_raw(payload):
    import json
    import subprocess
    return subprocess.run(
        [sys.executable, str(Path(__file__).parent / "check_agent_spawn.py")],
        input=json.dumps(payload), capture_output=True, text=True,
    )


def test_claude_payload_bad_title_blocks_with_exit_2():
    """Claude Code ignores a JSON deny; only exit 2 + stderr blocks the spawn."""
    out = _run_raw({"hook_event_name": "PreToolUse", "tool_name": "Agent",
                    "tool_input": {"subagent_type": "coder",
                                   "description": "bad title", "prompt": "x"}})
    assert out.returncode == 2
    assert "role(model): task" in out.stderr


def test_claude_payload_good_title_allows():
    out = _run_raw({"hook_event_name": "PreToolUse", "tool_name": "Agent",
                    "tool_input": {"subagent_type": "coder",
                                   "description": "coder(mid): build it", "prompt": "x"}})
    assert out.returncode == 0


def test_antigravity_payload_bad_title_denies_via_json():
    out = _run_raw({"toolCall": {"name": "invoke_subagent", "args": {
        "subagent_type": "coder", "description": "bad title", "prompt": "x"}}})
    assert out.returncode == 0
    assert '"decision": "deny"' in out.stdout


def _gp(type_name, title):
    args = {"description": title, "prompt": "do it", "model": "sonnet"}
    if type_name is not None:
        args["subagent_type"] = type_name
    return {"hook_event_name": "PreToolUse", "tool_name": "Agent", "tool_input": args}


@pytest.mark.parametrize("t", ["general-purpose", None, "Explore"])
def test_role_title_with_non_role_type_denied(t):
    r = evaluate(_gp(t, "coder(sonnet): build X"))
    assert r["decision"] == "deny"
    assert "subagent_type='coder'" in r["reason"]


def test_plain_title_general_purpose_allowed():
    assert evaluate(_gp("general-purpose", "Search the repo"))["decision"] == "allow"
