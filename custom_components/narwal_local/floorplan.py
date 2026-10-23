"""Map metres -> floor plan coordinates from three reference points.

Three point pairs fix an affine transform, so rotation, scale, mirroring and
offset between the robot's map and a drawn floor plan are all covered. The
floor plan side is in whatever unit the user enters (percent of the image
for Picture Elements cards, or pixels).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

CONF_FLOORPLAN = "floorplan"  # options key: [[map_x, map_y, plan_x, plan_y], ×3]


@dataclass(frozen=True, slots=True)
class Affine:
    """u = a·x + b·y + c, v = d·x + e·y + f."""

    a: float
    b: float
    c: float
    d: float
    e: float
    f: float

    @classmethod
    def from_points(cls, pairs: Sequence[Sequence[float]]) -> Affine:
        """Solve from three (map_x, map_y, plan_x, plan_y) pairs; raises
        ValueError when the map points lie on one line."""
        if len(pairs) != 3:
            raise ValueError("three reference points are needed")
        (x1, y1, u1, v1), (x2, y2, u2, v2), (x3, y3, u3, v3) = pairs
        det = x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2)
        if abs(det) < 1e-9:
            raise ValueError("the reference points lie on one line")

        def solve(w1: float, w2: float, w3: float) -> tuple[float, float, float]:
            # Cramer's rule for [x y 1]·[p q r]ᵀ = w at the three points.
            p = (w1 * (y2 - y3) + w2 * (y3 - y1) + w3 * (y1 - y2)) / det
            q = (x1 * (w2 - w3) + x2 * (w3 - w1) + x3 * (w1 - w2)) / det
            r = (x1 * (y2 * w3 - y3 * w2) + x2 * (y3 * w1 - y1 * w3) + x3 * (y1 * w2 - y2 * w1)) / det
            return p, q, r

        return cls(*solve(u1, u2, u3), *solve(v1, v2, v3))

    def apply(self, x: float, y: float) -> tuple[float, float]:
        return (self.a * x + self.b * y + self.c, self.d * x + self.e * y + self.f)


def affine_from_options(options: dict) -> Affine | None:
    """The configured transform, or None when the floor plan is not set up."""
    pairs = options.get(CONF_FLOORPLAN)
    if not pairs:
        return None
    try:
        return Affine.from_points(pairs)
    except (TypeError, ValueError):
        return None
