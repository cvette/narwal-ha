"""Minimal protobuf wire-format reader and writer.

Just enough for the Narwal messages: varints, length-delimited fields, fixed32
floats. It is not a general protobuf library and has no schema; callers pick
fields by number, mirroring the Go client's pbParse/pbWriter.
"""

from __future__ import annotations

from dataclasses import dataclass
import struct

WIRE_VARINT = 0
WIRE_FIXED64 = 1
WIRE_LEN = 2
WIRE_FIXED32 = 5


class ProtobufError(ValueError):
    """Raised when bytes are not a well-formed protobuf message."""


def encode_varint(value: int) -> bytes:
    """Encode an unsigned LEB128 varint. Negative values use 64-bit two's complement."""
    if value < 0:
        value &= (1 << 64) - 1
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def decode_varint(buf: bytes, pos: int = 0) -> tuple[int, int]:
    """Decode a varint at pos. Returns (value, new_pos)."""
    result = 0
    shift = 0
    while True:
        if pos >= len(buf):
            raise ProtobufError("truncated varint")
        byte = buf[pos]
        pos += 1
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return result, pos
        shift += 7
        if shift >= 70:
            raise ProtobufError("varint too long")


def to_int32(value: int) -> int:
    """Interpret a decoded varint as a signed int32 (negatives arrive as 64-bit)."""
    value &= 0xFFFFFFFF
    return value - (1 << 32) if value & 0x80000000 else value


@dataclass(frozen=True, slots=True)
class Field:
    """One decoded top-level field. value is an int for varints, else bytes."""

    num: int
    wtype: int
    value: int | bytes

    @property
    def int(self) -> int:
        if not isinstance(self.value, int):
            raise ProtobufError(f"field {self.num} is not a varint")
        return self.value

    @property
    def data(self) -> bytes:
        if not isinstance(self.value, bytes):
            raise ProtobufError(f"field {self.num} is not length-delimited")
        return self.value

    @property
    def float(self) -> float:
        if self.wtype != WIRE_FIXED32:
            raise ProtobufError(f"field {self.num} is not fixed32")
        return struct.unpack("<f", self.data)[0]

    @property
    def double(self) -> float:
        if self.wtype != WIRE_FIXED64:
            raise ProtobufError(f"field {self.num} is not fixed64")
        return struct.unpack("<d", self.data)[0]

    @property
    def text(self) -> str:
        return self.data.decode("utf-8", errors="replace")


def parse(buf: bytes) -> list[Field]:
    """Split a message body into its top-level fields."""
    fields: list[Field] = []
    pos = 0
    end = len(buf)
    while pos < end:
        key, pos = decode_varint(buf, pos)
        num, wtype = key >> 3, key & 7
        if num == 0:
            raise ProtobufError("field number 0")
        if wtype == WIRE_VARINT:
            value, pos = decode_varint(buf, pos)
            fields.append(Field(num, wtype, value))
        elif wtype == WIRE_LEN:
            length, pos = decode_varint(buf, pos)
            if pos + length > end:
                raise ProtobufError(f"field {num} truncated")
            fields.append(Field(num, wtype, bytes(buf[pos : pos + length])))
            pos += length
        elif wtype == WIRE_FIXED32:
            if pos + 4 > end:
                raise ProtobufError("short fixed32")
            fields.append(Field(num, wtype, bytes(buf[pos : pos + 4])))
            pos += 4
        elif wtype == WIRE_FIXED64:
            if pos + 8 > end:
                raise ProtobufError("short fixed64")
            fields.append(Field(num, wtype, bytes(buf[pos : pos + 8])))
            pos += 8
        else:
            raise ProtobufError(f"unsupported wire type {wtype}")
    return fields


def parse_packed_varints(buf: bytes) -> list[int]:
    """Decode a packed repeated varint field body."""
    out: list[int] = []
    pos = 0
    while pos < len(buf):
        value, pos = decode_varint(buf, pos)
        out.append(value)
    return out


class Writer:
    """Builds a message body. Zero/empty values are omitted unless forced,
    matching how the Dart protobuf runtime serializes defaults."""

    __slots__ = ("_buf",)

    def __init__(self) -> None:
        self._buf = bytearray()

    def __bytes__(self) -> bytes:
        return bytes(self._buf)

    def tag(self, num: int, wtype: int) -> Writer:
        self._buf += encode_varint(num << 3 | wtype)
        return self

    def varint(self, num: int, value: int, *, force: bool = False) -> Writer:
        if value or force:
            self.tag(num, WIRE_VARINT)
            self._buf += encode_varint(value)
        return self

    def int32(self, num: int, value: int, *, force: bool = False) -> Writer:
        """Signed int32/enum: negatives are sign-extended to 10 bytes like protobuf."""
        return self.varint(num, value, force=force)

    def boolean(self, num: int, value: bool) -> Writer:
        return self.varint(num, 1 if value else 0)

    def string(self, num: int, value: str) -> Writer:
        if value:
            self.bytes_(num, value.encode("utf-8"))
        return self

    def bytes_(self, num: int, value: bytes | None) -> Writer:
        if value is not None:
            self.tag(num, WIRE_LEN)
            self._buf += encode_varint(len(value))
            self._buf += value
        return self

    def message(self, num: int, body: bytes | Writer | None) -> Writer:
        if body is None:
            return self
        return self.bytes_(num, bytes(body))

    def float_(self, num: int, value: float) -> Writer:
        """fixed32 float, always written (map coordinates may be 0.0)."""
        self.tag(num, WIRE_FIXED32)
        self._buf += struct.pack("<f", value)
        return self

    def double(self, num: int, value: float) -> Writer:
        """fixed64 double, always written."""
        self.tag(num, WIRE_FIXED64)
        self._buf += struct.pack("<d", value)
        return self
