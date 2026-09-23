"""Tests for tools/version_bump.py (D-03/D-06): pure semver bump decision, no live git/Docker."""

import importlib.util
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parents[1] / "tools" / "version_bump.py"
_spec = importlib.util.spec_from_file_location("version_bump", _PATH)
version_bump = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(version_bump)


# --- decide_bump() priority order -------------------------------------------------------------

def test_breaking_change_wins_priority_over_feat_and_fix():
    lines = ['fix: something', 'feat: new thing', 'oops BREAKING CHANGE here']
    assert version_bump.decide_bump(lines) == 'major'


def test_feat_must_be_at_line_start():
    assert version_bump.decide_bump(['this is a feat: not really']) is None


def test_feat_with_scope_matches():
    assert version_bump.decide_bump(['feat(ui): new button']) == 'minor'


def test_fix_with_scope_matches():
    assert version_bump.decide_bump(['fix(db): leak']) == 'patch'


def test_no_match_returns_none():
    assert version_bump.decide_bump(['chore: tidy', 'docs: readme']) is None


def test_breaking_change_is_case_sensitive():
    assert version_bump.decide_bump(['breaking change lowercase']) is None


def test_multiline_commit_body_feat_line_detected_only_after_splitlines():
    # git log --pretty=%B returns one multi-line string in Python (unlike PowerShell's
    # automatic line array), so the caller must split it into lines before calling decide_bump().
    raw = 'chore: summary\n\nfeat: real change'
    assert version_bump.decide_bump(raw.splitlines()) == 'minor'
    assert version_bump.decide_bump([raw]) is None


# --- apply_bump() -------------------------------------------------------------------------------

def test_apply_bump_major():
    assert version_bump.apply_bump((1, 2, 3), 'major') == (2, 0, 0)


def test_apply_bump_minor():
    assert version_bump.apply_bump((1, 2, 3), 'minor') == (1, 3, 0)


def test_apply_bump_patch():
    assert version_bump.apply_bump((1, 2, 3), 'patch') == (1, 2, 4)


def test_apply_bump_unknown_type_raises():
    with pytest.raises(ValueError):
        version_bump.apply_bump((1, 2, 3), 'unknown')


# --- parse_version() ----------------------------------------------------------------------------

def test_parse_version_rejects_v_prefix():
    with pytest.raises(ValueError):
        version_bump.parse_version('v1.2.3')


def test_parse_version_rejects_wrong_part_count():
    with pytest.raises(ValueError):
        version_bump.parse_version('1.2')
    with pytest.raises(ValueError):
        version_bump.parse_version('1.2.3.4')


def test_parse_version_rejects_non_numeric():
    with pytest.raises(ValueError):
        version_bump.parse_version('1.2.x')
    with pytest.raises(ValueError):
        version_bump.parse_version('')


def test_parse_version_strips_whitespace():
    assert version_bump.parse_version(' 1.2.3\n') == (1, 2, 3)


def test_format_version_roundtrip():
    assert version_bump.format_version((1, 2, 3)) == '1.2.3'
    assert version_bump.parse_version(version_bump.format_version((4, 5, 6))) == (4, 5, 6)
