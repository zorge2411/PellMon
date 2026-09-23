"""Tests for tools/version_bump.py (D-03/D-06): pure semver bump decision, no live git/Docker."""

import importlib.util
import shutil
import subprocess
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


# --- repo-root VERSION file / configure.ac D-08 guard --------------------------------------------

def test_repo_version_file_is_well_formed():
    version_path = Path(__file__).resolve().parents[1] / 'VERSION'
    text = version_path.read_text()
    parsed = version_bump.parse_version(text)
    assert isinstance(parsed, tuple) and len(parsed) == 3
    assert all(isinstance(part, int) for part in parsed)
    assert not text.startswith('v')
    non_empty_lines = [line for line in text.splitlines() if line.strip()]
    assert len(non_empty_lines) == 1


def test_configure_ac_is_not_synced_with_version_file():
    configure_ac = Path(__file__).resolve().parents[1] / 'configure.ac'
    text = configure_ac.read_text()
    assert 'AC_INIT([PellMon], [0.7.0])' in text, (
        "D-08: VERSION is the sole source of truth for the Docker image tag only; "
        "configure.ac's Autotools version is deliberately not kept in sync."
    )


# --- git-backed integration tests (skipped if git is not installed) ------------------------------

needs_git = pytest.mark.skipif(shutil.which('git') is None, reason='git not installed')


def _init_repo(tmp_path):
    subprocess.run(['git', 'init'], cwd=str(tmp_path), check=True, capture_output=True)
    subprocess.run(['git', 'config', 'user.email', 'test@example.com'],
                    cwd=str(tmp_path), check=True, capture_output=True)
    subprocess.run(['git', 'config', 'user.name', 'Test'],
                    cwd=str(tmp_path), check=True, capture_output=True)


@needs_git
def test_last_tag_returns_none_in_a_repo_with_no_tags(tmp_path, monkeypatch):
    _init_repo(tmp_path)
    (tmp_path / 'a.txt').write_text('a')
    subprocess.run(['git', 'add', 'a.txt'], cwd=str(tmp_path), check=True, capture_output=True)
    subprocess.run(['git', 'commit', '-m', 'initial'], cwd=str(tmp_path), check=True,
                    capture_output=True)
    monkeypatch.chdir(tmp_path)
    # Pitfall 4: `git describe --tags --abbrev=0` exits non-zero here and must be tolerated,
    # not raised -- this repo genuinely has zero tags today, so this is the real first-run case.
    assert version_bump.last_tag() is None


@needs_git
def test_commits_since_no_tag_returns_full_history_lines(tmp_path, monkeypatch):
    _init_repo(tmp_path)
    (tmp_path / 'a.txt').write_text('a')
    subprocess.run(['git', 'add', 'a.txt'], cwd=str(tmp_path), check=True, capture_output=True)
    message = 'chore: summary\n\nfeat: real change'
    subprocess.run(['git', 'commit', '-m', message], cwd=str(tmp_path), check=True,
                    capture_output=True)
    monkeypatch.chdir(tmp_path)
    lines = version_bump.commits_since(None)
    assert 'feat: real change' in lines
    assert version_bump.decide_bump(lines) == 'minor'
