"""The map as an image entity, with the robot's live position."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Any

from homeassistant.components.image import ImageEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_call_later
from homeassistant.util import dt as dt_util

from .const import LIVE_MAP_INTERVAL
from .coordinator import NarwalConfigEntry, NarwalCoordinator
from .entity import NarwalEntity
from .map_objects import dirt_list, dock_room, furniture_list, obstacle_list
from .protocol import Activity, MapInfo, MapRenderer, Pose
from .protocol.render import Viewport, content_viewport

PARALLEL_UPDATES = 0

MAP_SCALE = 4  # pixels per map cell

# While these are active the robot is drawn with its current path.
ACTIVE = frozenset({Activity.CLEANING, Activity.PAUSED, Activity.RETURNING, Activity.ERROR})


def render_map(
    mi: MapInfo,
    robot: Pose | None = None,
    path: Sequence[tuple[float, float]] = (),
) -> bytes:
    """One-off render (diagnostics, scripts); the entity keeps a MapRenderer."""
    return MapRenderer(mi, MAP_SCALE).frame(robot, path)


def calibration_points(mi: MapInfo, vp: Viewport) -> list[dict[str, dict[str, int]]]:
    """Three image corners with their world position in millimetres, the
    `calibration_points` map cards use to turn a drawn zone into the
    coordinates of narwal_local.clean_zone."""
    points = []
    for col, row in ((vp.col0, vp.row0), (vp.col1, vp.row0), (vp.col0, vp.row1)):
        world = mi.cell_to_world(col, row)
        x, y = vp.corner(col, row)
        points.append(
            {
                "vacuum": {"x": round(world.x * 1000), "y": round(world.y * 1000)},
                "map": {"x": round(x), "y": round(y)},
            }
        )
    return points


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NarwalConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([NarwalMapImage(hass, entry.runtime_data)])


class NarwalMapImage(NarwalEntity, ImageEntity):
    """Rooms, walls, doors, carpets, no-go zones, furniture, camera
    detections, the dock and, during a clean, the robot and its path.

    The PNG is rendered on request and cached until the map or the robot's
    position changes; position changes refresh the image at most every
    LIVE_MAP_INTERVAL.
    """

    _attr_translation_key = "map"
    _attr_content_type = "image/png"

    def __init__(self, hass: HomeAssistant, coordinator: NarwalCoordinator) -> None:
        NarwalEntity.__init__(self, coordinator, "map")
        ImageEntity.__init__(self, hass)
        self._map_key = self._current_key()
        self._png: bytes | None = None
        self._png_key: tuple | None = None
        self._renderer: MapRenderer | None = None
        self._renderer_key: tuple | None = None
        self._last_live_bump: datetime | None = None
        self._pending_bump: Callable[[], None] | None = None
        self._robot_visible = self._overlay()[0] is not None
        self._calibration: tuple[tuple | None, list[dict[str, dict[str, int]]]] = (None, [])
        self._bounds: tuple[tuple | None, dict[int, tuple[float, float, float, float]]] = (None, {})
        if self._map_key is not None:
            self._attr_image_last_updated = dt_util.utcnow()

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self.coordinator.async_add_live_listener(self._handle_live))
        self.async_on_remove(self._cancel_pending_bump)

    def _current_key(self) -> tuple | None:
        mi = self.coordinator.data.map
        if mi is None or not mi.robot_has_map:
            return None
        return (
            mi.ref,
            tuple((r.id, r.name) for r in mi.rooms),
            tuple(mi.furniture),
            tuple(mi.obstacles),
            tuple(mi.dirt),
            mi.station,
        )

    def _overlay(self) -> tuple[Pose | None, tuple[tuple[float, float], ...]]:
        """What to draw on top of the map right now."""
        if self.coordinator.data.status.activity not in ACTIVE:
            return None, ()
        live = self.coordinator.live
        return live.robot, tuple(live.path)

    @property
    def available(self) -> bool:
        return super().available and self._map_key is not None

    @callback
    def _bump(self) -> None:
        self._attr_image_last_updated = dt_util.utcnow()

    @callback
    def _handle_coordinator_update(self) -> None:
        # Only map changes and the robot appearing or disappearing (a clean
        # starting or ending) refresh the image here; status pushes arrive
        # every second during a clean, movement goes through _handle_live.
        key = self._current_key()
        visible = self._overlay()[0] is not None
        if key != self._map_key or visible != self._robot_visible:
            self._map_key = key
            self._robot_visible = visible
            self._bump()
        super()._handle_coordinator_update()

    @callback
    def _handle_live(self) -> None:
        """The robot moved: refresh the image, at most every LIVE_MAP_INTERVAL."""
        if self._overlay()[0] is None or self._pending_bump is not None:
            return
        now = dt_util.utcnow()
        if self._last_live_bump is None or now - self._last_live_bump >= LIVE_MAP_INTERVAL:
            self._live_bump()
            return
        wait = (self._last_live_bump + LIVE_MAP_INTERVAL - now).total_seconds()
        self._pending_bump = async_call_later(self.hass, wait, self._live_bump)

    @callback
    def _live_bump(self, _now: datetime | None = None) -> None:
        self._pending_bump = None
        self._last_live_bump = dt_util.utcnow()
        self._robot_visible = self._overlay()[0] is not None
        self._bump()
        self.async_write_ha_state()

    @callback
    def _cancel_pending_bump(self) -> None:
        if self._pending_bump is not None:
            self._pending_bump()
            self._pending_bump = None

    async def async_image(self) -> bytes | None:
        mi = self.coordinator.data.map
        if mi is None or self._map_key is None:
            return None
        robot, path = self._overlay()
        key = (self._map_key, (robot, path))
        if self._png is not None and self._png_key == key:
            return self._png
        if self._renderer is None or self._renderer_key != self._map_key:
            # Base map, labels and icons: once per map version.
            self._renderer = await self.hass.async_add_executor_job(MapRenderer, mi, MAP_SCALE)
            self._renderer_key = self._map_key
        self._png = await self.hass.async_add_executor_job(self._renderer.frame, robot, path)
        self._png_key = key
        return self._png

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        mi = self.coordinator.data.map
        if mi is None:
            return None
        names = self.coordinator.data.names
        return {
            "map_id": mi.map_id,
            "rooms": self._rooms(mi),
            "dock_room": dock_room(mi),
            "furniture": furniture_list(mi, names),
            "obstacles": obstacle_list(mi, names),
            "dirt": dirt_list(mi, names),
            "calibration_points": self._calibration_points(mi),
        }

    def _rooms(self, mi: MapInfo) -> list[dict[str, Any]]:
        """Rooms with their bounding box in metres (cached per map version),
        handy reference points for a floor plan calibration."""
        key, bounds = self._bounds
        if key != self._map_key or (not bounds and mi.rooms):
            bounds = mi.room_bounds()
            self._bounds = (self._map_key, bounds)
        rooms = []
        for r in mi.rooms:
            room: dict[str, Any] = {"id": r.id, "name": r.name}
            if (box := bounds.get(r.id)) is not None:
                room["bounds"] = [round(v, 2) for v in box]
            rooms.append(room)
        return rooms

    def _calibration_points(self, mi: MapInfo) -> list[dict[str, dict[str, int]]]:
        """Cached per map version: finding the viewport scans the grid."""
        key, points = self._calibration
        if key != self._map_key or not points:
            points = calibration_points(mi, content_viewport(mi, MAP_SCALE)) if mi.robot_has_map else []
            self._calibration = (self._map_key, points)
        return points
