"""Automated AST enforcement gate against sys.path shims and implicit sibling imports (IMPORT-03).

Enforces:
1. Zero sys.path mutations (append, insert, extend, assign) anywhere in src/ runtime code (D-02).
2. All intra-package imports use explicit relative syntax (PEP 328) with level >= 1,
   and no implicit relative sibling imports (level == 0 matching sibling modules) remain
   in Scotteprotocol, scottecom, nbecom (including nbeprotocol), and yapsy, or across src/ (D-01, D-06).
"""

import ast
import pathlib
import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"

TARGET_PACKAGE_DIRS = [
    SRC_DIR / "Scotteprotocol",
    SRC_DIR / "Pellmonsrv" / "plugins" / "scottecom",
    SRC_DIR / "Pellmonsrv" / "plugins" / "nbecom",
    SRC_DIR / "Pellmonsrv" / "plugins" / "nbecom" / "nbeprotocol",
    SRC_DIR / "Pellmonsrv" / "yapsy",
]


def _is_sys_path_call(node: ast.Call) -> bool:
    """Check if an ast.Call node represents sys.path.append/insert/extend."""
    func = node.func
    if not isinstance(func, ast.Attribute):
        return False
    if func.attr not in ("append", "insert", "extend"):
        return False
    val = func.value
    # sys.path.append(...)
    if (
        isinstance(val, ast.Attribute)
        and isinstance(val.value, ast.Name)
        and val.value.id == "sys"
        and val.attr == "path"
    ):
        return True
    # path.append(...) where path is imported from sys
    if isinstance(val, ast.Name) and val.id == "path":
        return True
    return False


def _is_sys_path_assign(node: ast.AST) -> bool:
    """Check if an assignment targets sys.path or sys.path[...]."""
    if isinstance(node, (ast.Assign, ast.AugAssign)):
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for t in targets:
            if (
                isinstance(t, ast.Attribute)
                and isinstance(t.value, ast.Name)
                and t.value.id == "sys"
                and t.attr == "path"
            ):
                return True
            if (
                isinstance(t, ast.Subscript)
                and isinstance(t.value, ast.Attribute)
                and isinstance(t.value.value, ast.Name)
                and t.value.value.id == "sys"
                and t.value.attr == "path"
            ):
                return True
    return False


def _get_sibling_names(py_path: pathlib.Path) -> set:
    """Return module stems and subpackage names that are siblings of py_path."""
    pkg_dir = py_path.parent
    siblings = {
        p.stem
        for p in pkg_dir.glob("*.py")
        if p.name != "__init__.py" and not p.name.endswith(".py2bak") and p != py_path
    }
    siblings.update(
        {
            p.name
            for p in pkg_dir.iterdir()
            if p.is_dir() and (p / "__init__.py").is_file()
        }
    )
    return siblings


def find_sys_path_mutations(base_dir: pathlib.Path = SRC_DIR):
    """Walk all *.py files under base_dir (excluding .py2bak) and find sys.path mutations."""
    mutations = []
    for py_path in sorted(base_dir.rglob("*.py")):
        if py_path.name.endswith(".py2bak"):
            continue
        rel_path = py_path.relative_to(REPO_ROOT).as_posix()
        source = py_path.read_text(encoding="utf-8", errors="replace")
        try:
            tree = ast.parse(source, filename=str(py_path))
        except SyntaxError as exc:
            pytest.fail(f"Syntax error parsing {rel_path}: {exc}")

        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _is_sys_path_call(node):
                mutations.append((rel_path, node.lineno, ast.unparse(node.func)))
            elif _is_sys_path_assign(node):
                mutations.append((rel_path, node.lineno, "sys.path assignment"))
    return mutations


def find_implicit_sibling_imports(target_dirs=None):
    """Detect level==0 Import/ImportFrom where the target matches a sibling module or subpackage."""
    if target_dirs is None:
        target_dirs = [SRC_DIR]

    findings = []
    seen_paths = set()
    for directory in target_dirs:
        for py_path in sorted(directory.rglob("*.py")):
            if py_path in seen_paths or py_path.name.endswith(".py2bak"):
                continue
            seen_paths.add(py_path)
            rel_path = py_path.relative_to(REPO_ROOT).as_posix()
            siblings = _get_sibling_names(py_path)
            if not siblings:
                continue

            source = py_path.read_text(encoding="utf-8", errors="replace")
            try:
                tree = ast.parse(source, filename=str(py_path))
            except SyntaxError as exc:
                pytest.fail(f"Syntax error parsing {rel_path}: {exc}")

            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    if (node.level or 0) == 0 and node.module:
                        top = node.module.split(".")[0]
                        if top in siblings:
                            findings.append(
                                (
                                    rel_path,
                                    node.lineno,
                                    f"from {node.module} import ... (sibling: '{top}')",
                                )
                            )
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        top = alias.name.split(".")[0]
                        if top in siblings:
                            findings.append(
                                (
                                    rel_path,
                                    node.lineno,
                                    f"import {alias.name} (sibling: '{top}')",
                                )
                            )
    return findings


def test_no_sys_path_mutation_in_src():
    """IMPORT-03, D-02: Assert no sys.path shims or mutations exist in src/."""
    mutations = find_sys_path_mutations(SRC_DIR)
    assert not mutations, (
        f"Found {len(mutations)} sys.path mutation(s) in src/:\n"
        + "\n".join(f"  - {path}:{line} ({desc})" for path, line, desc in mutations)
    )


def test_no_implicit_sibling_imports_in_target_packages():
    """IMPORT-03, D-01: Assert no implicit sibling imports in Scotteprotocol, scottecom, nbecom, yapsy."""
    findings = find_implicit_sibling_imports(TARGET_PACKAGE_DIRS)
    assert not findings, (
        f"Found {len(findings)} implicit sibling import(s) in protocol/plugin packages:\n"
        + "\n".join(f"  - {path}:{line}: {stmt}" for path, line, stmt in findings)
    )


def test_no_implicit_sibling_imports_in_all_src():
    """IMPORT-03, D-01: Assert no implicit sibling imports exist anywhere in src/."""
    findings = find_implicit_sibling_imports([SRC_DIR])
    assert not findings, (
        f"Found {len(findings)} implicit sibling import(s) across src/:\n"
        + "\n".join(f"  - {path}:{line}: {stmt}" for path, line, stmt in findings)
    )


def test_detector_identifies_synthetic_violations():
    """Verify that the AST detection logic correctly catches sys.path calls and implicit sibling imports."""
    sample_code = """
import sys
from sys import path
sys.path.append("/some/path")
sys.path.insert(0, "/other/path")
path.extend(["/another/path"])
sys.path = ["/new/path"]

import sibling_mod
from sibling_mod import Thing
from .sibling_mod import SafeThing
import non_sibling
from . import sibling_subpkg
"""
    tree = ast.parse(sample_code)

    call_sites = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _is_sys_path_call(node):
            call_sites.append(node.lineno)
        elif _is_sys_path_assign(node):
            call_sites.append(node.lineno)

    assert len(call_sites) == 4, f"Expected 4 sys.path violations, got {len(call_sites)}"

    siblings = {"sibling_mod", "sibling_subpkg"}
    import_sites = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if (node.level or 0) == 0 and node.module:
                top = node.module.split(".")[0]
                if top in siblings:
                    import_sites.append((node.lineno, f"from {node.module}"))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top in siblings:
                    import_sites.append((node.lineno, f"import {alias.name}"))

    assert len(import_sites) == 2, f"Expected 2 sibling import violations, got {len(import_sites)}"
    assert import_sites[0][1] == "import sibling_mod"
    assert import_sites[1][1] == "from sibling_mod"
