"""Look up plugin widget templates without importing plugins (they need grp/pwd)."""
import ast
from pathlib import Path

PLUGINS = Path(__file__).resolve().parents[2] / "src" / "Pellmonsrv" / "plugins"


def find_template(name):
    for path in sorted(PLUGINS.glob("*/templates/%s" % name)):
        if path.is_file():
            return path.read_text(encoding="utf-8")
    for init in sorted(PLUGINS.glob("*/__init__.py")):
        tree = ast.parse(init.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "_insert_template" and len(node.args) >= 2
                    and isinstance(node.args[0], ast.Constant) and node.args[0].value == name
                    and isinstance(node.args[1], ast.Constant) and isinstance(node.args[1].value, str)):
                return node.args[1].value
    raise KeyError(name)
