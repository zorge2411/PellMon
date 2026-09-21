"""WR-07: the config editor script must not inject server/file-derived text as HTML."""

import re
from pathlib import Path

SOURCE_JS = Path(__file__).resolve().parents[2] / "src" / "Pellmonweb" / "media" / "js" / "source.js"


def test_source_js_uses_text_not_html_for_filenames_and_errors():
    js = SOURCE_JS.read_text(encoding="utf-8")
    assert not re.search(r"\.html\(", js), ".html() sink found in source.js; use .text()"
    assert "'<br>'+filedata.error" not in js
    assert ".text(filedata.filename)" in js
