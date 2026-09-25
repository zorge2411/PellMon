"""Regression tests for '%' in shipped configuration values.

The shipped conf.d files contain values with '%' (for example the RRD
datasource templates ``DS:%s:DERIVE:%u:0:U`` in database.conf, and
``owm4_unit = %`` in the openweathermap plugin config). Python 3's
ConfigParser interpolates '%' by default (Python 2 did not), which crashed
pellmonsrv at startup with InterpolationSyntaxError on a real Raspberry Pi.
The app parsers must be created with ``interpolation=None``.
"""

import logging
import pathlib
import re
import shutil

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
SRC = REPO / "src"

PARSER_FILES = [
    SRC / "Pellmonsrv" / "pellmonsrv.py",
    SRC / "Pellmonweb" / "pellmonweb.py",
    SRC / "Pellmonweb" / "pellmonconf.py",
]


def _install_conf_d(dest, localstatedir="/var"):
    """Prepare conf.d as DEPLOY-PI.md step 4a does (localstatedir is /var there;
    tests use a temp dir so the daemon can create its database directory)."""
    shutil.copytree(SRC / "conf.d", dest)
    (dest / "Makefile.am").unlink()
    for template in dest.glob("*.conf.in"):
        text = template.read_text(encoding="utf-8").replace("@localstatedir@", localstatedir)
        template.with_suffix("").write_text(text, encoding="utf-8")
        template.unlink()


@pytest.mark.parametrize("path", PARSER_FILES, ids=lambda p: p.name)
def test_app_parsers_disable_interpolation(path):
    """Source guard that also runs where dbus/gi are unavailable (Windows)."""
    source = path.read_text(encoding="utf-8")
    parsers = re.findall(r"configparser\.ConfigParser\(([^)]*)\)", source)
    assert parsers, "%s no longer builds a ConfigParser; update this test" % path.name
    for args in parsers:
        assert "interpolation=None" in args, (
            "%s builds a ConfigParser with interpolation enabled. Shipped config values "
            "contain '%%' (e.g. DS:%%s:DERIVE:%%u:0:U), which raises InterpolationSyntaxError "
            "at startup. Use configparser.ConfigParser(interpolation=None)." % path.name
        )


def test_pellmonsrv_reads_shipped_conf_d(tmp_path):
    """Instantiate the real daemon config against the shipped conf.d."""
    pytest.importorskip("dbus", reason="Pellmonsrv.pellmonsrv needs dbus (Linux only)")
    pytest.importorskip("gi", reason="Pellmonsrv.pellmonsrv needs gi (Linux only)")
    from Pellmonsrv import pellmonsrv

    conf_d = tmp_path / "conf.d"
    _install_conf_d(conf_d, localstatedir=(tmp_path / "var").as_posix())
    main = tmp_path / "pellmon.conf"
    main.write_text(
        "[conf]\nconfig_dir = %s\nlogfile = %s\n"
        % (conf_d.as_posix(), (tmp_path / "pellmon.log").as_posix()),
        encoding="utf-8",
    )

    logger = logging.getLogger("pellMon")
    handlers_before = list(logger.handlers)
    try:
        conf = pellmonsrv.config(str(main))
    finally:
        for handler in list(logger.handlers):
            if handler not in handlers_before:
                logger.removeHandler(handler)
                handler.close()

    assert conf.polling is True
    assert "ScotteCom" in conf.enabled_plugins
    # HomeAssistant is always loaded, exactly once, even if the conf lists it too
    assert conf.enabled_plugins.count("HomeAssistant") == 1
    assert "HomeAssistant" in conf.plugin_conf
    assert any("DERIVE" in part for part in conf.RrdCreateCommand)
    # the raw '%' must survive so the RRD template can be formatted later
    assert conf.plugin_conf["ScotteCom"]["serialport"] == "/dev/ttyUSB0"


def test_homeassistant_loaded_when_missing_from_enabled_plugins(tmp_path):
    """Installs whose enabled_plugins.conf predates Phase 6 still load HomeAssistant."""
    pytest.importorskip("dbus", reason="Pellmonsrv.pellmonsrv needs dbus (Linux only)")
    pytest.importorskip("gi", reason="Pellmonsrv.pellmonsrv needs gi (Linux only)")
    from Pellmonsrv import pellmonsrv

    conf_d = tmp_path / "conf.d"
    _install_conf_d(conf_d, localstatedir=(tmp_path / "var").as_posix())
    enabled = conf_d / "enabled_plugins.conf"
    text = enabled.read_text(encoding="utf-8").replace("p15 = HomeAssistant", "#p15 = HomeAssistant")
    enabled.write_text(text, encoding="utf-8")
    main = tmp_path / "pellmon.conf"
    main.write_text(
        "[conf]\nconfig_dir = %s\nlogfile = %s\n"
        % (conf_d.as_posix(), (tmp_path / "pellmon.log").as_posix()),
        encoding="utf-8",
    )

    logger = logging.getLogger("pellMon")
    handlers_before = list(logger.handlers)
    try:
        conf = pellmonsrv.config(str(main))
    finally:
        for handler in list(logger.handlers):
            if handler not in handlers_before:
                logger.removeHandler(handler)
                handler.close()

    assert conf.enabled_plugins.count("HomeAssistant") == 1
    assert conf.plugin_conf["HomeAssistant"] == {}
    assert "ScotteCom" in conf.enabled_plugins


def test_homeassistant_is_always_loaded_constant():
    src = (SRC / "Pellmonsrv" / "pellmonsrv.py").read_text(encoding="utf-8")
    assert "ALWAYS_LOADED_PLUGINS = ('HomeAssistant',)" in src
