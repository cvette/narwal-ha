"""Buttons: the station's actions (empty the dust box, wash or dry the mop)
and the cleaning plans saved in the Narwal app."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity, ButtonEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import NarwalConfigEntry, NarwalCoordinator, NarwalData
from .entity import NarwalEntity
from .protocol import CleanPlan, NarwalRobot

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class NarwalButtonDescription(ButtonEntityDescription):
    press_fn: Callable[[NarwalRobot], Awaitable[None]]
    exists_fn: Callable[[NarwalData], bool] = lambda _: True


BUTTONS: tuple[NarwalButtonDescription, ...] = (
    NarwalButtonDescription(key="empty_dust_bin", press_fn=lambda r: r.empty_dust_bin()),
    NarwalButtonDescription(key="wash_mop", press_fn=lambda r: r.wash_mop()),
    NarwalButtonDescription(key="dry_mop", press_fn=lambda r: r.dry_mop()),
    NarwalButtonDescription(key="wash_and_dry_mop", press_fn=lambda r: r.wash_and_dry_mop()),
    NarwalButtonDescription(
        key="dry_dust_bag",
        press_fn=lambda r: r.dry_dust_bag(),
        exists_fn=lambda d: d.status.has_field(21),  # the robot has its own dust bag
    ),
    NarwalButtonDescription(
        key="dry_station_bag",
        press_fn=lambda r: r.dry_station_bag(),
        exists_fn=lambda d: d.status.has_field(39),  # the station has a dust bag
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NarwalConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    if coordinator.data.status.has_station:
        async_add_entities(
            [
                *(NarwalStationButton(coordinator, d) for d in BUTTONS if d.exists_fn(coordinator.data)),
                NarwalContinueButton(coordinator),
            ]
        )

    async_add_entities([NarwalRestartButton(coordinator)])

    # Plans come and go in the app: add a button for each new one.
    known: set[int] = set()

    @callback
    def _add_new_plans() -> None:
        new = [p for p in coordinator.data.plans or () if p.id not in known]
        known.update(p.id for p in new)
        if new:
            async_add_entities(NarwalPlanButton(coordinator, p) for p in new)

    _add_new_plans()
    entry.async_on_unload(coordinator.async_add_listener(_add_new_plans))


class NarwalStationButton(NarwalEntity, ButtonEntity):
    """Starts a station action; the robot must be docked. Stop it with the
    vacuum's stop, like any task."""

    entity_description: NarwalButtonDescription

    def __init__(self, coordinator: NarwalCoordinator, description: NarwalButtonDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self._attr_translation_key = description.key

    async def async_press(self) -> None:
        await self.coordinator.async_command(self.entity_description.press_fn(self.coordinator.robot))
        await self.coordinator.async_request_refresh()


class NarwalPlanButton(NarwalEntity, ButtonEntity):
    """Starts a cleaning plan saved in the Narwal app. Unavailable once the
    plan is deleted there."""

    _attr_translation_key = "start_plan"

    def __init__(self, coordinator: NarwalCoordinator, plan: CleanPlan) -> None:
        super().__init__(coordinator, f"plan_{plan.id}")
        self._plan_id = plan.id
        self._attr_translation_placeholders = {"name": plan.name or str(plan.id)}

    @property
    def _plan(self) -> CleanPlan | None:
        return next((p for p in self.coordinator.data.plans or () if p.id == self._plan_id), None)

    @property
    def available(self) -> bool:
        return super().available and self._plan is not None

    async def async_press(self) -> None:
        if (plan := self._plan) is None:
            return
        await self.coordinator.async_command(self.coordinator.robot.start_plan(plan))
        await self.coordinator.async_request_refresh()


class NarwalContinueButton(NarwalEntity, ButtonEntity):
    """Resumes a clean that was interrupted (for example to recharge or by a
    stop); unavailable while there is nothing to resume."""

    _attr_translation_key = "continue_clean"

    def __init__(self, coordinator: NarwalCoordinator) -> None:
        super().__init__(coordinator, "continue_clean")

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data.continue_task is not None

    async def async_press(self) -> None:
        await self.coordinator.async_command(self.coordinator.robot.continue_task(True))
        await self.coordinator.async_request_refresh()


class NarwalRestartButton(NarwalEntity, ButtonEntity):
    """Restarts the robot's software (for when it hangs); the integration
    reconnects by itself."""

    _attr_device_class = ButtonDeviceClass.RESTART
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: NarwalCoordinator) -> None:
        super().__init__(coordinator, "restart")

    async def async_press(self) -> None:
        await self.coordinator.async_command(self.coordinator.robot.reboot())
