"""Source scan of the Home Assistant page script (T-06-34, T-06-35): text-only DOM writes."""

import re
from pathlib import Path

HA_JS = Path(__file__).resolve().parents[2] / "src" / "Pellmonweb" / "media" / "js" / "homeassistant.js"


def _js():
    return HA_JS.read_text(encoding="utf-8")


def test_script_has_no_html_sinks():
    js = _js()
    for sink in (r"\.html\(", r"innerHTML", r"outerHTML", r"insertAdjacentHTML", r"document\.write", r"\beval\("):
        assert not re.search(sink, js), "forbidden sink %s in homeassistant.js" % sink


def test_script_references_expected_contract():
    js = _js()
    for token in ("homeassistant/status", "homeassistant/test", "format", "Testing...", "Saving...",
                  "aria-busy", "tls_verify_field", "Test connection"):
        assert token in js, "%s missing from homeassistant.js" % token
    assert re.search(r"\b5000\b", js), "5000 ms status interval missing"
    assert re.search(r"TEST_ABORT_MS\s*=\s*12000\b", js), "12000 ms test abort missing"
    assert not re.search(r"\b10000\b", js), "test abort must not be 10000 ms"


def test_script_never_reads_or_writes_password_value():
    js = _js()
    assert "FormData(" in js
    # the password input is never looked up, so its value can neither be read nor copied to the DOM
    assert not re.search(r"""name=['"]?password""", js)
    assert not re.search(r"""getElementById\(\s*['"]password['"]""", js)
    assert not re.search(r"""\$\(\s*['"]#password""", js)
    assert not re.search(r"password[^\n]*\.value|\.value[^\n]*password", js, re.I)
