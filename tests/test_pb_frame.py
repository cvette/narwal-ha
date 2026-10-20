"""Wire format: varints, fields, frames, headers."""

from __future__ import annotations

import pytest

from protocol.frame import (
    SOURCE_APP,
    FrameError,
    Header,
    decode_frame,
    encode_frame,
    topic_of,
)
from protocol.pb import (
    ProtobufError,
    Writer,
    decode_varint,
    encode_varint,
    parse,
    parse_packed_varints,
    to_int32,
)


@pytest.mark.parametrize("value", [0, 1, 127, 128, 300, 2**32 - 1, 2**63])
def test_varint_roundtrip(value: int) -> None:
    assert decode_varint(encode_varint(value)) == (value, len(encode_varint(value)))


def test_negative_int32_is_ten_bytes_and_decodes_back() -> None:
    enc = encode_varint(-167)
    assert len(enc) == 10
    value, _ = decode_varint(enc)
    assert to_int32(value) == -167


def test_writer_omits_defaults_unless_forced() -> None:
    w = Writer().varint(1, 0).string(2, "").varint(3, 0, force=True)
    assert bytes(w) == b"\x18\x00"


def test_parse_mixed_fields() -> None:
    body = bytes(
        Writer().varint(1, 150).string(2, "hi").float_(3, 1.5).message(4, Writer().varint(1, 7))
    )
    fields = parse(body)
    assert [f.num for f in fields] == [1, 2, 3, 4]
    assert fields[0].int == 150
    assert fields[1].text == "hi"
    assert fields[2].float == 1.5
    assert parse(fields[3].data)[0].int == 7


def test_parse_rejects_truncated() -> None:
    with pytest.raises(ProtobufError):
        parse(b"\x12\x05ab")


def test_packed_varints() -> None:
    assert parse_packed_varints(encode_varint(1) + encode_varint(300)) == [1, 300]


def test_frame_roundtrip_with_multibyte_header_length() -> None:
    header = bytes(range(256)) + bytes(44)  # 300 bytes forces a 2-byte varint
    frame = encode_frame(header, b"payload-bytes")
    assert frame[0] == 0x01
    assert decode_frame(frame) == (header, b"payload-bytes")


@pytest.mark.parametrize("bad", [b"", b"\x01", b"\x02\x00", b"\x01\x05ab"])
def test_frame_rejects_bad_input(bad: bytes) -> None:
    with pytest.raises(FrameError):
        decode_frame(bad)


def test_header_roundtrip_keeps_source_app_on_wire() -> None:
    h = Header(
        url="/status/get_device_base_status",
        uuid="abc123",
        source=SOURCE_APP,
        response_url="/status/get_device_base_status/response",
        correlation_data="abc123",
        url_id=0x38,
    )
    raw = h.marshal()
    got = Header.parse(raw)
    assert (got.url, got.uuid, got.correlation_data, got.url_id) == (h.url, h.uuid, "abc123", 0x38)
    assert any(f.num == 3 for f in parse(raw)), "source (field 3) must be emitted"


@pytest.mark.parametrize(
    ("url", "topic"),
    [
        ("/pid0000000/0123456789abcdef0123456789abcdef/status/robot_base_status", "/status/robot_base_status"),
        ("/status/robot_base_status", "/status/robot_base_status"),
        ("/common/upgrade/check_firmware/response", "/common/upgrade/check_firmware/response"),
        ("/pid/did/upgrade/upgrade_status", "/upgrade/upgrade_status"),
    ],
)
def test_topic_of(url: str, topic: str) -> None:
    assert topic_of(url) == topic
