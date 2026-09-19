"""Round-trip and frame parsing tests for Scotteprotocol using loop:// serial transport."""

import pytest
import serial
from Scotteprotocol import Protocol
from Scotteprotocol.frames import FrameZ00, FrameZ01, FrameZ02, FrameZ03


def _make_synthetic_frame(frame, field_prefix="F"):
    """Generate a synthetic payload string matching a Frame's dataDef field lengths."""
    fields = []
    for idx, width in enumerate(frame.dataDef):
        val = f"{field_prefix}{idx:0{width - len(field_prefix)}d}" if width > len(field_prefix) else f"{idx:0{width}d}"
        fields.append(val[:width])
    return fields, "".join(fields)


def test_scotte_checksum_calculation_and_verification_str(loop_serial):
    """Verify addCheckSum and checkCheckSum on string inputs."""
    protocol = Protocol(None, "6.99", transport=loop_serial, start_thread=False)

    sample = "Z000000"
    checksummed = protocol.addCheckSum(sample)
    assert len(checksummed) == len(sample) + 1
    # 'Z' (90) XOR 6x '0' (48) = 90 = 'Z'
    assert checksummed == "Z000000Z"
    assert protocol.checkCheckSum(checksummed) == 0

    # Tampering with any character produces a nonzero checksum
    tampered = "Z000001Z"
    assert protocol.checkCheckSum(tampered) != 0

    # Additional standard frames and control messages
    for msg in ["OK", "E0", "E1", "Z010000", "Z020000", "Z030000"]:
        framed = protocol.addCheckSum(msg)
        assert protocol.checkCheckSum(framed) == 0
        corrupted = framed[:-1] + ("A" if framed[-1] != "A" else "B")
        assert protocol.checkCheckSum(corrupted) != 0


def test_scotte_checksum_deterministic_on_bytes(loop_serial):
    """Verify checksum calculation and verification behave identically on bytes and str."""
    protocol = Protocol(None, "6.99", transport=loop_serial, start_thread=False)

    msg_str = "Z000000"
    msg_bytes = b"Z000000"

    cs_from_str = protocol.addCheckSum(msg_str)
    cs_from_bytes = protocol.addCheckSum(msg_bytes)
    assert cs_from_str == cs_from_bytes
    assert isinstance(cs_from_str, str)

    # Verification on byte input
    raw_with_cs_bytes = cs_from_str.encode("latin-1")
    assert protocol.checkCheckSum(raw_with_cs_bytes) == 0

    # Tampered byte input
    tampered_bytes = b"Z000001Z"
    assert protocol.checkCheckSum(tampered_bytes) != 0


def test_scotte_checksum_disabled(loop_serial):
    """Verify that when checksum is disabled, addCheckSum passes through and checkCheckSum returns 0."""
    protocol = Protocol(None, "6.99", transport=loop_serial, start_thread=False)
    protocol.checksum = False

    msg = "Z000000"
    assert protocol.addCheckSum(msg) == msg
    assert protocol.checkCheckSum(msg) == 0
    assert protocol.checkCheckSum("any_string") == 0


@pytest.mark.parametrize(
    "frame, name",
    [
        (FrameZ00, "FrameZ00"),
        (FrameZ01, "FrameZ01"),
        (FrameZ02, "FrameZ02"),
        (FrameZ03, "FrameZ03"),
    ],
)
def test_scotte_frame_parsing_roundtrip(loop_serial, frame, name):
    """Verify per-frame-type encode and decode logic parses synthetic data correctly."""
    protocol = Protocol(None, "6.99", transport=loop_serial, start_thread=False)

    fields, raw_payload = _make_synthetic_frame(frame)
    assert len(raw_payload) == frame.frameLength

    full_frame = protocol.addCheckSum(raw_payload)
    assert len(full_frame) == frame.getLength(protocol)

    parsed_ok = frame.parse(full_frame, protocol)
    assert parsed_ok is True

    for idx, expected_val in enumerate(fields):
        assert frame.get(idx) == expected_val


def test_scotte_frame_z00_getitem_integration(loop_serial):
    """Verify that FrameZ00 parsed values flow through to Protocol.getItem correctly."""
    protocol = Protocol(None, "6.99", transport=loop_serial, start_thread=False)

    # Build FrameZ00 payload with known numeric values for specific sensors:
    # boiler_temp: index 2, decimals 1 -> 00655 -> 65.5
    # chute_temp: index 3, decimals 0 -> 00042 -> 42
    # oxygen: index 5, decimals 1 -> 00123 -> 12.3
    fields, _ = _make_synthetic_frame(FrameZ00, field_prefix="0")
    fields[2] = "00655"  # 65.5 C boiler_temp
    fields[3] = "00042"  # 42 C chute_temp
    fields[5] = "00123"  # 12.3 % oxygen
    raw_payload = "".join(fields)

    full_frame = protocol.addCheckSum(raw_payload)
    assert FrameZ00.parse(full_frame, protocol) is True

    # Read parsed values via protocol.getItem without triggering serial poll
    assert protocol.getItem("boiler_temp") == "65.5"
    assert protocol.getItem("chute_temp") == "42"
    assert protocol.getItem("oxygen") == "12.3"


def test_scotte_frame_parse_error_rejection(loop_serial):
    """Verify Frame.parse rejects checksum errors, error frames, and invalid lengths."""
    protocol = Protocol(None, "6.99", transport=loop_serial, start_thread=False)

    _, raw_payload = _make_synthetic_frame(FrameZ00)
    valid_frame = protocol.addCheckSum(raw_payload)

    # 1. Tampered checksum
    tampered_frame = valid_frame[:-1] + ("X" if valid_frame[-1] != "X" else "Y")
    assert FrameZ00.parse(tampered_frame, protocol) is False

    # 2. Tampered payload byte with intact trailing byte
    tampered_body = "X" + valid_frame[1:]
    assert FrameZ00.parse(tampered_body, protocol) is False

    # 3. Error response E0 (checksum failure response from burner)
    e0_frame = protocol.addCheckSum("E0")
    assert FrameZ00.parse(e0_frame, protocol) is False

    # 4. Error response E1 (data does not exist response from burner)
    e1_frame = protocol.addCheckSum("E1")
    assert FrameZ00.parse(e1_frame, protocol) is False

    # 5. Wrong length payload
    short_payload = protocol.addCheckSum("Z001234")
    assert FrameZ00.parse(short_payload, protocol) is False


def test_scotte_serial_loop_transport_roundtrip(loop_serial):
    """Verify communication over loop:// serial transport with Protocol."""
    protocol = Protocol(None, "6.99", transport=loop_serial, start_thread=False)
    assert protocol.ser is loop_serial
    assert protocol.dummyDevice is False

    # Write a poll command through protocol transport
    command = protocol.addCheckSum("Z000000")
    encoded_command = command.encode("latin-1")
    protocol.ser.write(encoded_command)

    # Read back from the loopback transport
    read_back = protocol.ser.read(len(encoded_command)).decode("latin-1")
    assert read_back == command
    assert protocol.checkCheckSum(read_back) == 0

    # Write response frame and read it back
    _, raw_payload = _make_synthetic_frame(FrameZ02)
    response_frame = protocol.addCheckSum(raw_payload)
    protocol.ser.write(response_frame.encode("latin-1"))

    expected_len = FrameZ02.getLength(protocol)
    received_bytes = protocol.ser.read(expected_len)
    received_str = received_bytes.decode("latin-1")

    assert received_str == response_frame
    assert FrameZ02.parse(received_str, protocol) is True
