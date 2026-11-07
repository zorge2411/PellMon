"""Source scan of the Backup page script: text-only DOM writes and the polling contract."""

import re
from pathlib import Path

JS = Path(__file__).resolve().parents[2] / "src" / "Pellmonweb" / "media" / "js" / "backup.js"


def _js():
    return JS.read_text(encoding="utf-8")


def test_backup_js_no_html_sinks():
    js = _js()
    for sink in (r"\.html\(", r"innerHTML", r"outerHTML", r"insertAdjacentHTML", r"document\.write", r"\beval\("):
        assert not re.search(sink, js), "forbidden sink %s in backup.js" % sink


def test_backup_js_contract():
    js = _js()
    for token in ("backup-restore", "data-url", "getAttribute", "textContent", "Restarting the server",
                  "success", "warning", "danger"):
        assert token in js, "%s missing from backup.js" % token
    assert re.search(r"INTERVAL_MS\s*=\s*2000\b", js)
