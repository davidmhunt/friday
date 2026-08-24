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
