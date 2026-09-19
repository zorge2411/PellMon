"""Automated enforcement gate against ad hoc print() calls (OBS-03).

Implements ROADMAP Phase 2 success criterion 4:
Enforces that no ad hoc print() calls remain in src/Pellmonsrv or src/Pellmonweb
runtime code. All runtime logging must use the shared logging.getLogger('pellMon')
logger at appropriate severity levels.

The only sanctioned print() calls are the three CLI startup banner lines in
src/Pellmonweb/pellmonconf.py (D-04).
"""

import ast
import pathlib
import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SEARCH_DIRS = [
    REPO_ROOT / "src" / "Pellmonsrv",
    REPO_ROOT / "src" / "Pellmonweb",
]

# Allowed surviving print() sites (D-04):
# These three sites are the manually-invoked standalone CLI tool's startup banner
# in src/Pellmonweb/pellmonconf.py. They are intentionally exempted from the OBS-03
# print sweep because they provide direct terminal output to the user who ran the CLI.
# Widening this allowlist requires a documented decision (e.g. in .planning/phases/),
# not a convenience edit.
ALLOWED_PRINTS = (
    ("src/Pellmonweb/pellmonconf.py", "Open http://<ip>:%u"),
    ("src/Pellmonweb/pellmonconf.py", "Run as root to be able to save changes"),
    ("src/Pellmonweb/pellmonconf.py", "Quit with CTRL-C"),
)


def _get_call_first_str_arg(node: ast.Call):
    """Extract literal string or format string prefix from the first call argument."""
    if not node.args:
        return None
    arg0 = node.args[0]
    if isinstance(arg0, ast.Constant) and isinstance(arg0.value, str):
        return arg0.value
    if isinstance(arg0, ast.BinOp) and isinstance(arg0.left, ast.Constant) and isinstance(arg0.left.value, str):
        return arg0.left.value
    return None


class _PrintFinder(ast.NodeVisitor):
    def __init__(self, rel_path):
        self.rel_path = rel_path
        self.scope_stack = []
        self.print_calls = []

    def visit_ClassDef(self, node):
        self.scope_stack.append(node.name)
        self.generic_visit(node)
        self.scope_stack.pop()

    def visit_FunctionDef(self, node):
        self.scope_stack.append(node.name)
        self.generic_visit(node)
        self.scope_stack.pop()

    def visit_AsyncFunctionDef(self, node):
        self.scope_stack.append(node.name)
        self.generic_visit(node)
        self.scope_stack.pop()

    def visit_Call(self, node):
        if isinstance(node.func, ast.Name) and node.func.id == "print":
            first_str = _get_call_first_str_arg(node)
            self.print_calls.append((self.rel_path, node.lineno, first_str))
        self.generic_visit(node)


def _find_print_calls():
    """Parse all python files under SEARCH_DIRS and yield (rel_path, lineno, first_str_arg)."""
    for search_dir in SEARCH_DIRS:
        for py_path in sorted(search_dir.rglob("*.py")):
            if py_path.name.endswith(".py2bak"):
                continue
            rel_path = py_path.relative_to(REPO_ROOT).as_posix()
            source = py_path.read_text(encoding="utf-8", errors="replace")
            try:
                tree = ast.parse(source, filename=str(py_path))
            except SyntaxError as exc:
                pytest.fail(f"Syntax error parsing {rel_path}: {exc}")
            finder = _PrintFinder(rel_path)
            finder.visit(tree)
            yield from finder.print_calls


def _matches_allowlist(rel_path, first_str):
    for allowed_path, fragment in ALLOWED_PRINTS:
        if rel_path == allowed_path and first_str is not None and fragment in first_str:
            return (allowed_path, fragment)
    return None


def test_no_ad_hoc_print_calls_in_runtime_code():
    """OBS-03: Assert no print() calls remain in src/Pellmonsrv or src/Pellmonweb
    except the allowlisted CLI banner lines."""
    disallowed = []
    for rel_path, lineno, first_str in _find_print_calls():
        matched = _matches_allowlist(rel_path, first_str)
        if not matched:
            disallowed.append(f"{rel_path}:{lineno} (arg preview: {first_str!r})")

    assert not disallowed, (
        f"Found {len(disallowed)} disallowed print() call(s) in runtime code:\n"
        + "\n".join(f"  - {site}" for site in disallowed)
    )


def test_print_allowlist_is_not_vacuous():
    """Assert all allowlisted banner sites are actually present in pellmonconf.py."""
    matched_allowlist = set()
    for rel_path, _, first_str in _find_print_calls():
        matched = _matches_allowlist(rel_path, first_str)
        if matched:
            matched_allowlist.add(matched)

    missing = set(ALLOWED_PRINTS) - matched_allowlist
    assert not missing, (
        f"The following allowlisted print() sites were not found in source:\n"
        + "\n".join(f"  - {path}: fragment {fragment!r}" for path, fragment in missing)
    )
