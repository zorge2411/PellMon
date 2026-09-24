"""Drift guard for the browser-test stub server (Windows-safe: no Pellmonweb import)."""
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "browser"))

import plugin_templates  # noqa: E402


def _run_globals():
    tree = ast.parse((ROOT / "src" / "Pellmonweb" / "pellmonweb.py").read_text(encoding="utf-8"))
    names = set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "run":
            for sub in ast.walk(node):
                if isinstance(sub, ast.Global):
                    names.update(sub.names)
    return names


def test_stub_sets_every_global_assigned_in_run():
    names = _run_globals()
    assert names, "no globals found in pellmonweb.run(); guard is broken"
    stub = (ROOT / "tests" / "browser" / "stub_server.py").read_text(encoding="utf-8")
    missing = sorted(n for n in names if ("web.%s = " % n) not in stub)
    assert not missing, "stub_server.py does not set pellmonweb.run() globals: %s" % ", ".join(missing)


def test_plugin_templates_lookup():
    assert plugin_templates.find_template("consumption").strip()
    assert plugin_templates.find_template("silolevel").strip()
    expected = (ROOT / "src" / "Pellmonsrv" / "plugins" / "consumption" / "templates" / "consumption7d").read_text(encoding="utf-8")
    assert plugin_templates.find_template("consumption7d") == expected
