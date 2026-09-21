"""The daemon's log level must default to INFO.

On a real Raspberry Pi with no `loglevel` in the config, pellmonsrv logged every serial
frame at DEBUG (dozens of lines per poll), which filled the persisted log folder and wore
the SD card. A missing or invalid `[conf] loglevel` now means INFO; `debug` is opt-in.
"""

import logging
import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent


def _build_config(tmp_path, loglevel_line, caplog):
    pytest.importorskip("dbus", reason="Pellmonsrv.pellmonsrv needs dbus (Linux only)")
    pytest.importorskip("gi", reason="Pellmonsrv.pellmonsrv needs gi (Linux only)")
    from Pellmonsrv import pellmonsrv

    main = tmp_path / "pellmon.conf"
    main.write_text(
        "[conf]\nlogfile = %s\n%s" % ((tmp_path / "pellmon.log").as_posix(), loglevel_line),
        encoding="utf-8",
    )
    logger = logging.getLogger("pellMon")
    level_before = logger.level
    handlers_before = list(logger.handlers)
    try:
        with caplog.at_level(logging.DEBUG):
            pellmonsrv.config(str(main))
        return logger.level
    finally:
        logger.setLevel(level_before)
        for handler in list(logger.handlers):
            if handler not in handlers_before:
                logger.removeHandler(handler)
                handler.close()


def test_missing_loglevel_defaults_to_info(tmp_path, caplog):
    assert _build_config(tmp_path, "", caplog) == logging.INFO


def test_loglevel_info(tmp_path, caplog):
    assert _build_config(tmp_path, "loglevel = info\n", caplog) == logging.INFO


def test_loglevel_debug_is_still_available(tmp_path, caplog):
    assert _build_config(tmp_path, "loglevel = debug\n", caplog) == logging.DEBUG


def test_invalid_loglevel_falls_back_to_info_with_a_warning(tmp_path, caplog):
    level = _build_config(tmp_path, "loglevel = verbose\n", caplog)
    assert level == logging.INFO
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING and "verbose" in r.getMessage()]
    assert warnings, "an invalid loglevel value must be reported once, naming the bad value"


def test_example_config_sets_info():
    text = (REPO / "config" / "pellmon.conf.example").read_text(encoding="utf-8")
    uncommented = [line.strip() for line in text.splitlines() if not line.lstrip().startswith("#")]
    assert "loglevel = info" in uncommented, "config/pellmon.conf.example must set loglevel = info"
