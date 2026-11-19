"""tt-01 (#24): a pre-approved explicit tag push runs while a directive is active; friday check
errors on a listed git push the guard always denies."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_preapproved import DIRECTIVE, allowed_section, fc, make_repo, pre  # noqa: E402

LISTED = ["git push origin refs/tags/known-good/x", "git push origin tag known-good/x",
          "git push --tags", "git push origin +refs/tags/x", "git push origin refs/tags/x main",
          "git push origin main"]


@pytest.fixture
def repo(tmp_path, monkeypatch):
    r = make_repo(tmp_path, monkeypatch, LISTED)
    fc.write_marker(r, {"id": "core-01", "goal_base": "main"})
    return r


@pytest.fixture
def unlisted(tmp_path, monkeypatch):
    r = make_repo(tmp_path, monkeypatch, ["friday nodes --clean"])
    fc.write_marker(r, {"id": "core-01", "goal_base": "main"})
    return r


def test_listed_tag_push_allowed(repo):
    d, why = pre(repo, "git push origin refs/tags/known-good/x")
    assert d == "allow" and "pre-approved" in why


def test_listed_tag_form_allowed(repo):
    assert pre(repo, "git push origin tag known-good/x")[0] == "allow"


def test_unlisted_tag_push_denied_with_message(unlisted):
    d, why = pre(unlisted, "git push origin refs/tags/known-good/x")
    assert d == "deny" and "tag push" in why and "## Allowed commands" in why


@pytest.mark.parametrize("cmd", [
    "git push --tags", "git push origin +refs/tags/x", "git push origin refs/tags/x main",
    "git push origin main",
])
def test_listed_but_still_denied(repo, cmd):
    assert pre(repo, cmd)[0] == "deny"


def _errs(pat, did="core-01"):
    text = DIRECTIVE.format(allowed=allowed_section([pat]))
    return [i.message for i in fc.validate_directive(did, text) if i.level == "error"]


@pytest.mark.parametrize("pat", ["git push origin main", "git push origin *"])
def test_check_errors_on_listed_branch_push(pat):
    errs = _errs(pat)
    assert any("push guard denies" in m or "deny list" in m for m in errs), errs


@pytest.mark.parametrize("pat", ["git push origin friday/core-01 refs/tags/a",
                                 "git push origin refs/tags/a friday/core-01"])
def test_check_errors_on_mixed_tag_and_branch_push(pat):
    errs = _errs(pat)
    assert any("mixing tag and branch" in m for m in errs), errs


@pytest.mark.parametrize("pat", ["git push origin refs/tags/known-good/*", "git push origin tag known-good/x",
                                 "git push origin friday/core-01"])
def test_check_accepts_tag_and_goal_branch_push(pat):
    assert _errs(pat) == []
