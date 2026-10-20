"""Wire frames and the Header message.

One WebSocket binary message is one frame (device_channel NrPbWireFormat):

    byte 0       marker, always 0x01
    bytes 1..k   header length, unsigned LEB128 varint
    next hdrLen  serialized Header protobuf
    remainder    payload protobuf (its length is implied by the frame size)
"""

from __future__ import annotations

from dataclasses import dataclass

from .pb import Writer, decode_varint, encode_varint, parse

FRAME_MARKER = 0x01

# Header_Source values.
SOURCE_APP = 0
SOURCE_HILINK = 1
SOURCE_LLM = 2
SOURCE_AIOT = 3


class FrameError(ValueError):
    """Raised for a malformed frame."""


def encode_frame(header: bytes, payload: bytes) -> bytes:
    return bytes([FRAME_MARKER]) + encode_varint(len(header)) + header + payload


def decode_frame(frame: bytes) -> tuple[bytes, bytes]:
    """Split a frame into (header bytes, payload bytes)."""
    if len(frame) < 2:
        raise FrameError("frame too short")
    if frame[0] != FRAME_MARKER:
        raise FrameError(f"bad frame marker 0x{frame[0]:02x}")
    try:
        hdr_len, pos = decode_varint(frame, 1)
    except ValueError as err:
        raise FrameError("bad header length varint") from err
    if len(frame) - pos < hdr_len:
        raise FrameError("header out of length")
    return frame[pos : pos + hdr_len], frame[pos + hdr_len :]


@dataclass(slots=True)
class Header:
    """app_protol Header: {1 extendedString, 2 uuid, 3 source, 4 url,
    5 properties{1 responseUrl, 2 correlationData}, 6 urlId}."""

    url: str = ""
    uuid: str = ""
    source: int = SOURCE_APP
    response_url: str = ""
    correlation_data: str = ""
    extended_string: str = ""
    url_id: int = 0
    has_properties: bool = False

    def marshal(self) -> bytes:
        w = Writer()
        w.string(1, self.extended_string)
        w.string(2, self.uuid)
        w.int32(3, self.source, force=True)  # APP=0 is still put on the wire
        w.string(4, self.url)
        if self.has_properties or self.response_url or self.correlation_data:
            props = Writer().string(1, self.response_url).string(2, self.correlation_data)
            w.message(5, props)
        w.int32(6, self.url_id)
        return bytes(w)

    @classmethod
    def parse(cls, buf: bytes) -> Header:
        h = cls()
        for f in parse(buf):
            if f.num == 1:
                h.extended_string = f.text
            elif f.num == 2:
                h.uuid = f.text
            elif f.num == 3:
                h.source = f.int
            elif f.num == 4:
                h.url = f.text
            elif f.num == 5:
                h.has_properties = True
                for p in parse(f.data):
                    if p.num == 1:
                        h.response_url = p.text
                    elif p.num == 2:
                        h.correlation_data = p.text
            elif f.num == 6:
                h.url_id = f.int
        return h


def topic_of(url: str) -> str:
    """Strip the /<pid>/<did> prefix from a pushed topic.

    Pushes arrive as /<pid>/<did>/<group>/<name>; replies to our calls use the
    bare service url, which itself may have three segments
    (/common/upgrade/check_firmware). Service urls have at most three, so the
    prefix is dropped only when four or more segments are present.
    """
    parts = url.strip("/").split("/")
    if parts and parts[-1] == "response":
        core, suffix = parts[:-1], ["response"]
    else:
        core, suffix = parts, []
    if len(core) >= 4:
        core = core[2:]
    return "/" + "/".join(core + suffix)
