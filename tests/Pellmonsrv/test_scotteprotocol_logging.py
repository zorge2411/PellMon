"""Tests for Scotteprotocol imports, database initialization, and exception logging."""

import logging
import pytest
import serial
import Scotteprotocol
from Scotteprotocol import Protocol
import Pellmonsrv.plugins.scottecom as scottecom_mod


def test_scotteprotocol_import_and_dummy_database():
    """Verify Scotteprotocol imports and dummy device initializes database properly."""
    protocol = Protocol(None, '6.99')
    assert protocol.dummyDevice is True
    assert len(protocol.dataBase) > 0
    assert "power" in protocol.dataBase
    assert protocol.getItem("power") == "1234"
    assert protocol.setItem("power", "50") == "OK"


def test_scotteprotocol_serial_open_failure_logs_exception(monkeypatch, caplog):
    """Verify serial port open failure logs via logger.exception with exc_info attached."""
    def mock_open(self):
        raise serial.SerialException("Mocked serial open failure")

    monkeypatch.setattr(serial.Serial, "open", mock_open)

    with caplog.at_level(logging.ERROR, logger="pellMon"):
        protocol = Protocol("/dev/nonexistent_burner", "6.99")

    error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert error_records, "Expected an ERROR-level record when serial port open fails"
    record = error_records[0]
    assert record.exc_info is not None
    assert record.exc_info[0] is serial.SerialException
    assert "Could not open serial port" in record.getMessage()
    assert protocol.dummyDevice is True


def test_scotteprotocol_set_item_unexpected_error_logs_exception(caplog):
    """Verify unexpected errors during setItem log via logger.exception with exc_info attached."""
    protocol = Protocol(None, "6.99")
    protocol.dummyDevice = False
    protocol.ser = None

    class FaultyQueue:
        def put(self, *args, **kwargs):
            raise RuntimeError("Simulated command queue crash")

    protocol.q = FaultyQueue()

    with caplog.at_level(logging.ERROR, logger="pellMon"):
        protocol.setItem("feeder_capacity", "1000")

    error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert error_records, "Expected an ERROR-level record on unexpected setItem error"
    record = error_records[0]
    assert record.exc_info is not None
    assert record.exc_info[0] is RuntimeError
    assert "Unexpected error in setItem" in record.getMessage()


def test_scottecom_plugin_import_and_instantiation():
    """Verify Pellmonsrv.plugins.scottecom imports and instantiates cleanly."""
    plugin = scottecom_mod.scottecom()
    assert plugin is not None
    assert hasattr(plugin, "activate")
