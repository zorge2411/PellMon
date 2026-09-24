---
phase: 10
slug: optimize-for-mobile-devices-screen-size
status: planned
nyquist_compliant: false
wave_0_complete: false
created: 2026-09-24
---

# Phase 10 - Validation Strategy

> Per-phase validation contract. Source: 10-RESEARCH.md "Validation Architecture".

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x (+ pytest-mock, pytest-socket); browser layer adds playwright 1.63.0 |
| **Config file** | `pytest.ini` (`pythonpath = src`, `testpaths = tests`, `addopts = --disable-socket`), unchanged |
| **Quick run command** | `venv-py3/Scripts/python.exe -m pytest tests/Pellmonweb/test_mobile_layout.py tests/test_ci_docker_config.py -q` |
| **Full suite command** | `pytest tests/ -v` (browser tests skip when `PELLMON_BROWSER_TESTS` is unset) |
| **Browser command (CI/WSL)** | `PELLMON_BROWSER_TESTS=1 PYTHONPATH=src pytest tests/browser -v -rs --allow-unix-socket` |
| **Estimated runtime** | quick ~2 s; browser ~1-2 min in CI |

## Sampling Rate

- **After every task commit:** quick command (Windows-safe, structural only).
- **After every plan wave:** `pytest tests/ -v` locally; for CSS/JS/template waves also the browser command in WSL or CI.
- **Before verify-work:** full suite green including the CI browser step, then the D-06(c) manual real-phone checkpoint.
- **Max feedback latency:** ~5 s (structural), ~2 min (browser).

## Per-Requirement Verification Map

| Req | Behavior | Test type | Automated command | File exists |
|-----|----------|-----------|-------------------|-------------|
| D-01 | No new framework; BS3 classes only, no new stylesheet/link | structural | `pytest tests/Pellmonweb/test_mobile_layout.py -k "framework or css_block"` | Wave 0 |
| D-02 | No horizontal overflow at 390 and 768 on 6 pages; body/html not `overflow-x:hidden`; 1280 smoke | browser | `pytest tests/browser/test_mobile_overflow.py` | Wave 0 |
| D-03 | Order/size of systemimage; events collapsed with toggle; single column at 390/768 | browser + structural | `pytest tests/browser/test_mobile_interactions.py -k main` | Wave 0 |
| D-04 | `.pellmon-graph`/`.pellmon-chart` heights 260/320/400; no inline 400px in the 6 sources; tap targets >= 44px | structural + browser | structural checks + browser B4/B5/B7/E1 | Wave 0 |
| D-05 | Parameters sections/pills/inputs; Settings 2-up; 44px buttons | structural + browser | structural + browser C1-C3/D1-D2/E2-E3 | Wave 0 |
| D-06(a) | Structural pytest checks | unit | `pytest tests/Pellmonweb/test_mobile_layout.py` | Wave 0 |
| D-06(b) | Browser checks mandatory in CI | CI guard | `pytest tests/test_ci_docker_config.py` (new asserts; existing guards still pass) | modify existing |
| D-06(c) | Real phone check via stoker.schoeler.pro | manual | human-verify checkpoint | n/a |
| D-07 | `index.html` uses `12 // len(row)`; desktop renders side by side at 1280 | structural + browser | structural + 1280 smoke check | Wave 0 |

## Wave 0 Requirements

- [ ] Spike: prove `pytest tests/browser --allow-unix-socket` launches Playwright under `--disable-socket` (else `-o addopts=""`).
- [ ] `requirements-browser.txt` (`playwright==1.63.0`), kept out of the Docker image.
- [ ] `tests/Pellmonweb/test_mobile_layout.py` (structural checks + stub-drift guard).
- [ ] `tests/browser/{conftest.py, stub_server.py, fake_dbus.py, plugin_templates.py, test_mobile_overflow.py, test_mobile_interactions.py}`.
- [ ] `tests/test_ci_docker_config.py`: add browser-step assertions only (do not touch existing ones; `--force` and `needs: test` guards stay valid).
- [ ] `.gitignore`: `tests/browser/_shots/`; `tests/README.md`: document `--allow-unix-socket` and `PELLMON_BROWSER_TESTS`.

## Manual-Only Verifications

| Behavior | Requirement | Why manual | Instructions |
|----------|-------------|------------|--------------|
| Real phone rendering (iOS Safari `aspect-ratio` on `<object>`, touch targets, no sideways scroll) | D-06(c) | CI tests Chromium only | Open `https://stoker.schoeler.pro/` on a phone: main page, graph controls, events toggle, Parameters sections, Settings 2-up gallery; also check the desktop side-by-side layout (D-07) |

## Validation Sign-Off

- [ ] All tasks have automated verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
