"""Write tests/fixtures/get_map.bin: a made-up GetMap_Response.

It has the same structure as a real robot's map (gzip grid of packed varints,
room infos, border frame, doors, carpets, a no-carpet area and a forbidden
zone) but an invented floor plan, so no real home is published. Regenerate the
Go golden output afterwards with the Go client's cmd/mapgolden.

    python scripts/make_synthetic_map.py
"""

from __future__ import annotations

import gzip
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
import conftest  # noqa: E402,F401  (loads the `protocol` package)

from protocol.pb import Writer, encode_varint  # noqa: E402

WIDTH, HEIGHT = 120, 100
RESOLUTION_MM = 50
ORIGIN = (-3.0, -2.5)
BORDER_LEFT, BORDER_BOTTOM = -40, -30  # border-frame cell = display cell + border

ROOMS = {  # id: (name, col0, row0, col1, row1) inclusive, stored rows (0 = bottom)
    1: ("Living room", 10, 10, 59, 49),
    2: ("Kitchen", 61, 10, 99, 49),
    3: ("Hallway", 10, 51, 99, 60),
    4: ("Bedroom", 10, 62, 69, 89),
}
DOORS = [  # (room a, room b, cells of the gap)
    (1, 2, [(60, r) for r in range(28, 33)]),
    (1, 3, [(c, 50) for c in range(30, 35)]),
    (3, 4, [(c, 61) for c in range(40, 45)]),
]
CARPETS = {1: (20, 20, 35, 30), 2: (30, 70, 50, 80)}  # id: display rect
NO_CARPETS = {1: (70, 20, 80, 25)}
FORBIDDEN = (1, 3, (85, 35, 95, 45))  # id, type SWEEP_MOP, display rect (cells)

WALL = 0x01  # room 0 with a flag bit: wall/obstacle
ROOM_FLAGS = 0x02


def grid() -> list[int]:
    cells = [0] * (WIDTH * HEIGHT)
    for _name, c0, r0, c1, r1 in ROOMS.values():  # walls around every room
        for c in range(c0 - 1, c1 + 2):
            for r in range(r0 - 1, r1 + 2):
                cells[r * WIDTH + c] = WALL
    for rid, (_name, c0, r0, c1, r1) in ROOMS.items():
        for c in range(c0, c1 + 1):
            for r in range(r0, r1 + 1):
                cells[r * WIDTH + c] = rid << 8 | ROOM_FLAGS
    for a, _b, gap in DOORS:  # open the wall in the doorway
        for c, r in gap:
            cells[r * WIDTH + c] = a << 8 | ROOM_FLAGS
    return cells


def cell_point(col: int, row: int) -> Writer:
    """Integer point in the border frame."""
    return Writer().varint(1, col + BORDER_LEFT).varint(2, row + BORDER_BOTTOM)


def world_point(col: float, row: float) -> Writer:
    res = RESOLUTION_MM / 1000
    return Writer().float_(1, ORIGIN[0] + col * res).float_(2, ORIGIN[1] + row * res)


def rect(c0: int, r0: int, c1: int, r1: int) -> list[tuple[int, int]]:
    return [(c0, r0), (c1, r0), (c1, r1), (c0, r1)]


def main() -> None:
    packed = b"".join(encode_varint(v) for v in grid())
    grid_blob = gzip.compress(bytes(Writer().bytes_(1, packed)), mtime=0)

    m = Writer()
    m.varint(1, 1).varint(2, 7).varint(3, RESOLUTION_MM).varint(4, WIDTH).varint(5, HEIGHT)
    m.message(
        6,
        Writer()
        .varint(1, BORDER_BOTTOM)
        .varint(2, BORDER_BOTTOM + HEIGHT - 1)
        .varint(3, BORDER_LEFT)
        .varint(4, BORDER_LEFT + WIDTH - 1),
    )
    m.message(7, Writer().float_(1, ORIGIN[0]).float_(2, ORIGIN[1]))

    fid, ftype, frect = FORBIDDEN
    fa = Writer()
    for c, r in rect(*frect):
        fa.message(1, world_point(c, r))
    m.message(9, fa.varint(2, ftype).varint(3, fid))

    for a, b, gap in DOORS:
        door = Writer().bytes_(1, encode_varint(a) + encode_varint(b))
        door.message(2, cell_point(*gap[0])).message(2, cell_point(*gap[-1]))
        m.message(11, door)

    for rid, (name, *_rest) in ROOMS.items():
        m.message(12, Writer().varint(1, rid).string(3, name))

    m.bytes_(17, grid_blob).varint(18, 3)

    for cid, r in CARPETS.items():
        carpet = Writer().varint(1, cid)
        for c, rr in rect(*r):
            carpet.message(2, cell_point(c, rr))
        m.message(26, carpet)

    m.varint(33, 12)

    for nid, r in NO_CARPETS.items():
        area = Writer().varint(1, nid)
        for c, rr in rect(*r):
            area.message(2, cell_point(c, rr))
        m.message(51, area)

    response = Writer().varint(1, 1).message(2, m).varint(3, 1)
    out = ROOT / "tests" / "fixtures" / "get_map.bin"
    out.write_bytes(bytes(response))
    print(f"wrote {out} ({len(bytes(response))} bytes)")


if __name__ == "__main__":
    main()
