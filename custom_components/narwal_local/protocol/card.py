"""Data for the interactive map card: the base map and how to draw on it.

Kept free of Home Assistant so the card's demo page can be generated from a
map file (see scripts/make_card_demo.py).
"""

from __future__ import annotations

import base64
from typing import Any

from .map import CELL_UNKNOWN, CELL_WALL, MapInfo, Point
from .render import MapRenderer, Viewport

MAP_SCALE = 4  # pixels per map cell, as the image entity


def map_version(mi: MapInfo) -> str:
    """Changes whenever anything the base map shows changes."""
    key = (
        mi.ref,
        tuple((r.id, r.name) for r in mi.rooms),
        tuple(mi.furniture),
        tuple(mi.obstacles),
        tuple(mi.dirt),
        mi.station,
    )
    return f"{hash(key) & 0xFFFFFFFF:08x}"


def _room_grid(mi: MapInfo, vp: Viewport) -> bytes:
    """Room id per cell of the viewport, top image row first; 0 = no room."""
    grid, w = mi.room_grid(), mi.width
    out = bytearray()
    for row in range(vp.row1 - 1, vp.row0 - 1, -1):
        base = row * w
        for col in range(vp.col0, vp.col1):
            v = grid[base + col]
            out.append(0 if v in (CELL_UNKNOWN, CELL_WALL) or v > 254 else v)
    return bytes(out)


def _px(mi: MapInfo, vp: Viewport, p: Point) -> list[float]:
    """Border-frame point -> image pixels."""
    c = mi.border_point_to_cell(p.x, p.y)
    return [round(v, 1) for v in vp.corner(c.col, c.row)]


def build_map_payload(mi: MapInfo) -> dict[str, Any]:
    """The static part of the card's map (runs in the executor)."""
    renderer = MapRenderer(mi, MAP_SCALE)
    vp = renderer.viewport
    width, height = vp.size
    bounds = mi.room_bounds()
    return {
        "version": map_version(mi),
        "image": "data:image/png;base64," + base64.b64encode(renderer.frame()).decode(),
        "width": width,
        "height": height,
        # px = ((x - origin_x) / resolution - col0) * scale
        # py = (row1 - (y - origin_y) / resolution) * scale
        "transform": {
            "origin_x": mi.origin_x,
            "origin_y": mi.origin_y,
            "resolution": mi.resolution_m,
            "col0": vp.col0,
            "row1": vp.row1,
            "scale": vp.scale,
        },
        "rooms": [
            {"id": r.id, "name": r.name, "bounds": [round(v, 3) for v in bounds.get(r.id, ())]}
            for r in mi.rooms
        ],
        "no_go_zones": [
            {
                "id": fa.id,
                "type": int(fa.type),
                "points": [_px(mi, vp, p) for p in fa.polygon],
            }
            for fa in mi.forbiddens
        ],
        "grid": {
            "width": vp.col1 - vp.col0,
            "height": vp.row1 - vp.row0,
            "data": base64.b64encode(_room_grid(mi, vp)).decode(),
        },
    }
