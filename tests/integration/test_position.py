"""Position sensor and the floor plan calibration (options flow)."""

from __future__ import annotations

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.narwal_local.floorplan import CONF_FLOORPLAN, Affine, affine_from_options
from custom_components.narwal_local.protocol import TaskType

from .conftest import FakeRobot, display_map_payload, status_payload

POSITION = "sensor.narwal_position"
CLEANING = {1: TaskType.SWEEP_AND_MOP, 6: 7}
# Synthetic map: origin (-3, -2.5) m, 50 mm cells; display cell (45, 20) is
# (-0.75, -1.5) m in the living room. The dock is at (-1.25, -0.075) m facing -y.
CALIBRATION = [[0, 0, 10, 90], [1, 0, 20, 90], [0, 1, 10, 80]]  # u = 10 + 10x, v = 90 - 10y


def test_affine_handles_rotation_and_mirroring() -> None:
    # Plan = map rotated by 90°, scaled by 2, mirrored in y, shifted.
    def plan(x: float, y: float) -> tuple[float, float]:
        return (5 - 2 * y, 7 - 2 * x)

    pts = [(0, 0), (3, 1), (-2, 4)]
    affine = Affine.from_points([[x, y, *plan(x, y)] for x, y in pts])
    for x, y in [(1.5, -2), (10, 10)]:
        assert affine.apply(x, y) == pytest.approx(plan(x, y))
    with pytest.raises(ValueError):
        Affine.from_points([[0, 0, 0, 0], [1, 1, 1, 1], [2, 2, 5, 5]])
    assert affine_from_options({}) is None


async def test_docked_position(hass: HomeAssistant, init_integration) -> None:
    state = hass.states.get(POSITION)
    assert float(state.state) == 0.0, "distance from the dock"
    assert state.attributes["x"] == pytest.approx(-1.25)
    assert state.attributes["y"] == pytest.approx(-0.075)
    assert state.attributes["heading"] == 270
    assert "floorplan_x" not in state.attributes


async def test_position_follows_the_robot_with_throttle(
    hass: HomeAssistant, init_integration, robot: FakeRobot, freezer: FrozenDateTimeFactory
) -> None:
    robot.push("/status/robot_base_status", status_payload(CLEANING))
    await hass.async_block_till_done()
    freezer.tick(timedelta(seconds=2))
    written: list[tuple] = []
    hass.bus.async_listen(
        "state_changed",
        lambda e: written.append((e.data["new_state"].attributes.get("x"), e.data["new_state"].attributes.get("y")))
        if e.data["entity_id"] == POSITION and e.data["new_state"] is not None
        else None,
    )
    robot.push("/map/display_map", display_map_payload(45, 20))
    robot.push("/map/display_map", display_map_payload(50, 20))  # within a second: skipped
    await hass.async_block_till_done()
    state = hass.states.get(POSITION)
    assert (state.attributes["x"], state.attributes["y"]) == (pytest.approx(-0.75), pytest.approx(-1.5))
    assert state.attributes["room"] == "Living room"
    assert float(state.state) == pytest.approx(1.51, abs=0.01)
    assert len(written) == 1

    freezer.tick(timedelta(seconds=2))
    robot.push("/map/display_map", display_map_payload(45.5, 20))  # 2.5 cm: not worth a write
    await hass.async_block_till_done()
    assert len(written) == 1
    freezer.tick(timedelta(seconds=2))
    robot.push("/map/display_map", display_map_payload(50, 20))
    await hass.async_block_till_done()
    assert len(written) == 2 and written[-1][0] == pytest.approx(-0.5)


async def _options(hass: HomeAssistant, entry: MockConfigEntry, values: dict) -> dict:
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(result["flow_id"], values)
    await hass.async_block_till_done()
    return result


def _fields(pairs: list[list[float]]) -> dict[str, float]:
    names = ("map_x", "map_y", "plan_x", "plan_y")
    return {f"p{i}_{n}": v for i, pair in enumerate(pairs, start=1) for n, v in zip(names, pair, strict=True)}


async def test_floorplan_calibration(hass: HomeAssistant, init_integration: MockConfigEntry) -> None:
    result = await _options(hass, init_integration, _fields(CALIBRATION))
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert init_integration.options == {CONF_FLOORPLAN: CALIBRATION}

    state = hass.states.get(POSITION)
    assert state.attributes["floorplan_x"] == pytest.approx(10 + 10 * -1.25)
    assert state.attributes["floorplan_y"] == pytest.approx(90 - 10 * -0.075, abs=0.01)
    assert state.attributes["floorplan_heading"] == 90, "facing -y on the map is down on the plan"

    result = await _options(hass, init_integration, {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert init_integration.options == {}
    assert "floorplan_x" not in hass.states.get(POSITION).attributes


@pytest.mark.parametrize(
    ("values", "error"),
    [
        ({"p1_map_x": 1.0}, "incomplete_points"),
        (_fields([[0, 0, 1, 1], [1, 1, 2, 2], [2, 2, 3, 3]]), "points_on_a_line"),
    ],
)
async def test_floorplan_calibration_errors(
    hass: HomeAssistant, init_integration: MockConfigEntry, values: dict, error: str
) -> None:
    result = await _options(hass, init_integration, values)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}


async def test_room_bounds_on_the_map(hass: HomeAssistant, init_integration) -> None:
    rooms = hass.states.get("image.narwal_map").attributes["rooms"]
    assert rooms[0] == {"id": 1, "name": "Living room", "bounds": [-2.5, -2.0, 0.05, 0.05]}
