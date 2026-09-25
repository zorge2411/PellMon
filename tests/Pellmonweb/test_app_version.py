"""The app version from the VERSION file is shown on every page and in the image."""
import os
import re

from mako.lookup import TemplateLookup

from Pellmonweb.appversion import get_version

REPO = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '..'))
HTML = os.path.join(REPO, 'src', 'Pellmonweb', 'html')


def _version_file():
    with open(os.path.join(REPO, 'VERSION')) as f:
        return f.read().strip()


def test_get_version_matches_version_file():
    assert get_version() == _version_file()
    assert re.match(r'^\d+\.\d+\.\d+$', get_version())


def test_get_version_falls_back_to_dev(tmp_path):
    assert get_version(str(tmp_path / 'missing')) == 'dev'
    empty = tmp_path / 'VERSION'
    empty.write_text('\n')
    assert get_version(str(empty)) == 'dev'


def test_layout_footer_shows_version_on_every_page():
    lookup = TemplateLookup(directories=[HTML], input_encoding='utf-8')
    out = lookup.get_template('about.html').render(
        username=None, webroot='', version=get_version())
    assert 'PellMon v%s' % _version_file() in out
    assert 'app-version' in out


def test_dockerfile_copies_version_file():
    with open(os.path.join(REPO, 'Dockerfile')) as f:
        assert 'COPY VERSION ./VERSION' in f.read()
    with open(os.path.join(REPO, '.dockerignore')) as f:
        assert not any(l.strip() == 'VERSION' for l in f)
