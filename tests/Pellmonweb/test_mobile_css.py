"""Phase 10 structural checks for the responsive block in pellmon.css (text assertions, Windows-safe)."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MEDIA = ROOT / "src" / "Pellmonweb" / "media"
CSS = MEDIA / "css" / "pellmon.css"
LAYOUT = ROOT / "src" / "Pellmonweb" / "html" / "layout.html"
HEADER = "/* Phase 10: mobile / responsive */"
ALLOWED_QUERIES = (
    "(max-width: 767px)",
    "(min-width: 768px) and (max-width: 991px)",
    "(min-width: 768px)",
)


def phase10_block():
    text = CSS.read_text(encoding="utf-8")
    idx = text.find(HEADER)
    if idx < 0:
        return ""
    return text[idx:]


def media_blocks(text):
    """Return (query, body) pairs for every top-level @media in text, using brace counting."""
    result = []
    pos = 0
    while True:
        start = text.find("@media", pos)
        if start < 0:
            break
        open_idx = text.find("{", start)
        query = text[start + len("@media"):open_idx].strip()
        depth = 1
        i = open_idx + 1
        while i < len(text) and depth:
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
            i += 1
        result.append((query, text[open_idx + 1:i - 1]))
        pos = i
    return result


def strip_media(text):
    """Return text with every @media block removed (the un-queried base rules)."""
    out = []
    pos = 0
    for query, body in media_blocks(text):
        start = text.find("@media", pos)
        out.append(text[pos:start])
        pos = start + len("@media") + text[start + len("@media"):].find("{") + 1 + len(body) + 1
    out.append(text[pos:])
    return "".join(out)


def rule_body(text, selector):
    m = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", text)
    return m.group(1) if m else ""


def test_framework_bs3_only_no_new_stylesheet():
    layout = LAYOUT.read_text(encoding="utf-8")
    links = re.findall(r'<link[^>]*href="\$\{webroot\}/media/[^"]*"[^>]*rel="stylesheet"[^>]*>', layout)
    hrefs = [re.search(r'href="([^"]*)"', l).group(1) for l in links]
    assert hrefs == [
        "${webroot}/media/bs3/css/bootstrap.min.css",
        "${webroot}/media/css/pellmon.css",
    ], "D-01: layout.html must link exactly Bootstrap and pellmon.css, got %r" % hrefs
    bs = (MEDIA / "bs3" / "css" / "bootstrap.css").read_text(encoding="utf-8")
    assert "v3.0.0" in bs[:200], "D-01: Bootstrap must stay the vendored 3.0.0"
    files = sorted(p.name for p in (MEDIA / "css").iterdir() if p.is_file())
    assert files == ["pellmon.css", "pellmonconf.css", "pellmonconf_print.css"], (
        "D-01: no new stylesheet allowed, got %r" % files)


def test_css_block_header_and_values():
    block = phase10_block()
    for needle in (HEADER, "max-width: 767px", "min-height: 44px", ".pellmon-graph",
                   ".pellmon-chart", "260px", "320px", "400px", "#events-wrap.events-collapsed",
                   "aspect-ratio: 11 / 7", ".param-section-toggle", ".param-tags", ".sysimg-save"):
        assert needle in block, "UI-SPEC check 8: Phase 10 block missing %r" % needle


def test_css_block_preserves_existing_rules():
    text = CSS.read_text(encoding="utf-8")
    idx = text.find(HEADER)
    before = text if idx < 0 else text[:idx]
    for needle in (".sysimg-tile {", ".dl-horizontal dt", "@media (min-width: 768px)", "object {"):
        assert needle in before, "D-01: pre-Phase-10 rule %r must be preserved" % needle


def test_css_block_media_queries_are_bounded():
    block = phase10_block()
    assert block, "UI-SPEC check 8: Phase 10 block missing"
    queries = [q for q, _ in media_blocks(block)]
    assert queries, "UI-SPEC check 8: Phase 10 block has no media queries"
    for q in queries:
        assert q in ALLOWED_QUERIES, "UI-SPEC breakpoints: unexpected media query %r" % q


def test_css_block_no_overflow_masking():
    text = CSS.read_text(encoding="utf-8")
    assert not re.search(r"overflow-x\s*:\s*hidden", text), "D-02: overflow-x hidden must not mask overflow"


def test_css_block_spacing_scale():
    block = phase10_block()
    assert block, "UI-SPEC Spacing Scale: Phase 10 block missing"
    allowed = {0, 4, 8, 16, 24}
    for m in re.finditer(r"(?<![\w-])(padding|margin|gap)(?:-[a-z]+)?\s*:\s*([^;}]*)", block):
        value = m.group(2)
        if "calc(" in value:
            continue
        for num in re.findall(r"(-?\d+(?:\.\d+)?)px", value):
            assert float(num) in allowed, (
                "UI-SPEC Spacing Scale: %s value %spx not in 0/4/8/16/24" % (m.group(1), num))


def test_css_block_chart_heights_per_breakpoint():
    block = phase10_block()
    assert block, "D-04: Phase 10 block missing"
    selector = ".pellmon-graph, .pellmon-chart"
    blocks = dict(media_blocks(block))
    phone = rule_body(blocks.get("(max-width: 767px)", ""), selector)
    tablet = rule_body(blocks.get("(min-width: 768px) and (max-width: 991px)", ""), selector)
    base = rule_body(strip_media(block), selector)
    assert "height: 260px" in phone, "D-04: phone graph height must be 260px"
    assert "height: 320px" in tablet, "D-04: tablet graph height must be 320px"
    assert "height: 400px" in base, "D-04: desktop graph height must stay 400px"
