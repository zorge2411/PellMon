"""Gate: src/pellmoncli.in must be valid Python 3 (not imported: needs gi)."""
import ast
import pathlib
import re

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = (REPO_ROOT / "src" / "pellmoncli.in").read_text(encoding="utf-8")


def test_compiles():
    compile(SRC, "pellmoncli.in", "exec")


def test_no_py2_names():
    bad = {'raw_input', 'unicode', 'basestring', 'xrange', 'long'}
    tree = ast.parse(SRC)
    found = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and n.id in bad}
    assert not found


def test_no_py2_idioms():
    assert not re.search(r'\.iteritems\(|\.iterkeys\(|\.itervalues\(|\.has_key\(', SRC)
    assert not re.search(r'except\s+\w+\s*,\s*\w+\s*:', SRC)


def test_no_tab_indentation():
    assert not re.search(r'^[ ]*\t', SRC, re.M)
