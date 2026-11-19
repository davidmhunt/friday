"""`## Rules` on directives and goals and `rules` in friday.json reach every implementer and reviewer prompt."""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib"))
import friday_core as fc  # noqa: E402
sys.path.insert(0, str(ROOT / "tests"))
import test_execute_prompts as tp  # noqa: E402

DIRECTIVE = """# tt-99: demo
Status: approved
Goal: g1
Node: any
Deliverable: code
Verify: true
Hardware: none

## Goal
x

## Steps
1. do it

## Rules
- shared rule
- directive rule
- shared rule

## Out of scope
- nothing

## Log
"""
GOAL = """# g1: demo goal
Status: approved
Base: main
Land: goal

## Directives
1. tt-99: demo

## Rules
- goal rule
- shared rule
"""


def _repo(tmp_path, cfg):
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "friday.json").write_text(json.dumps(cfg))
    (tmp_path / "docs" / "directives").mkdir(parents=True)
    (tmp_path / "docs" / "goals").mkdir(parents=True)
    (tmp_path / "docs" / "directives" / "tt-99.md").write_text(DIRECTIVE)
    (tmp_path / "docs" / "goals" / "g1.md").write_text(GOAL)
    return tmp_path


def test_parse_json_merges_orders_and_dedups(tmp_path):
    r = _repo(tmp_path, {"rules": ["repo rule", "shared rule"]})
    subprocess.run(["git", "init", "-q"], cwd=r, check=True)
    p = subprocess.run([sys.executable, str(ROOT / "bin" / "friday"), "parse", "tt-99", "--json"],
                       cwd=r, capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout)["rules"] == ["repo rule", "shared rule", "goal rule", "directive rule"]


def test_merged_rules_without_config(tmp_path):
    assert fc.merged_rules(tmp_path, ["a", "b"], ["b", "c"]) == ["a", "b", "c"]


def test_empty_rules_section_is_an_error():
    for validate, name, text in ((fc.validate_directive, "tt-99", DIRECTIVE), (fc.validate_goal, "g1", GOAL)):
        bad = re.sub(r"(## Rules\n).*", r"\1", text, flags=re.S)
        errs = [i for i in validate(name, bad) if i.level == "error" and "Rules" in i.message]
        assert errs, name
        assert not [i for i in validate(name, text) if "Rules" in i.message]


def test_non_list_rules_is_a_check_error(tmp_path):
    r = _repo(tmp_path, {"rules": "be nice"})
    assert any(i.level == "error" and "rules" in i.message for i in fc.config_issues(r))
    assert any(i.level == "error" and "rules" in i.message for i in fc.check_repo(r))


def test_list_rules_is_fine(tmp_path):
    assert fc.config_issues(_repo(tmp_path, {"rules": ["a"]})) == []


def test_rules_block_in_every_implementer_and_reviewer_prompt():
    found = set()
    for body in tp._agent_prompts():
        for key in ("Implement step", "Review friday directive", "Second review", "its Verify command fails", "found these gaps"):
            if key in body:
                found.add(key)
                assert "${rulesBlock(d.rules)}" in body, key
    assert found == {"Implement step", "Review friday directive", "Second review", "its Verify command fails", "found these gaps"}


def test_reviewers_treat_broken_rule_as_gap():
    for body in tp._agent_prompts():
        if "Review friday directive" in body or "Second review" in body:
            assert "${RULE_GAP(d.rules)}" in body
    assert "A broken rule is a gap" in tp.SRC


def test_duplicate_rules_section_is_an_error():
    dup_d = DIRECTIVE.replace("## Out of scope", "## Rules\n- second\n\n## Out of scope", 1)
    dup_g = GOAL + "\n## Rules\n- second\n"
    for validate, name, text in ((fc.validate_directive, "tt-99", dup_d), (fc.validate_goal, "g1", dup_g)):
        assert [i for i in validate(name, text) if i.level == "error" and "duplicate section `## Rules`" in i.message], name
