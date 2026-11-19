"""hardware_approval in .claude/friday.json: command|session, known resources only."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib"))
import friday_core as fc  # noqa: E402


def _repo(tmp_path, cfg):
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "friday.json").write_text(json.dumps(cfg))
    return tmp_path


HW = {"radar": [r"\bflash\b"], "gpu": ["train"]}


def test_valid_values_accepted(tmp_path):
    r = _repo(tmp_path, {"hardware": HW, "hardware_approval": {"radar": "session", "gpu": "command"}})
    assert fc.config_issues(r) == []
    assert fc.load_config(r)["hardware_approval"] == {"radar": "session", "gpu": "command"}


def test_absent_is_fine(tmp_path):
    assert fc.config_issues(_repo(tmp_path, {"hardware": HW})) == []


def test_bad_value_and_unknown_resource_rejected(tmp_path):
    r = _repo(tmp_path, {"hardware": HW, "hardware_approval": {"radar": "always", "nope": "session"}})
    msgs = [i.message for i in fc.config_issues(r)]
    assert any("always" in m for m in msgs) and any("nope" in m for m in msgs)
    assert all(i.level == "error" for i in fc.config_issues(r))
    assert fc.load_config(r)["hardware_approval"] == {}
    assert any(i.level == "error" for i in fc.check_repo(r))


def test_non_object_rejected(tmp_path):
    r = _repo(tmp_path, {"hardware": HW, "hardware_approval": ["radar"]})
    assert fc.config_issues(r)
