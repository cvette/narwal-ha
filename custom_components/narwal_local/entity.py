"""Base entity."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import NarwalCoordinator


class NarwalEntity(CoordinatorEntity[NarwalCoordinator]):
    """Ties every entity to the one robot device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: NarwalCoordinator, key: str) -> None:
        super().__init__(coordinator)
        static = coordinator.static
        self._attr_unique_id = f"{coordinator.device_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.device_id)},
            manufacturer=MANUFACTURER,
            name=MANUFACTURER,
            sw_version=(static.firmware.version_text if static.firmware else None)
            or static.device.firmware_version
            or None,
        )
