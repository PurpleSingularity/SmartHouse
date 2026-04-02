import logging
from datetime import UTC, datetime
from uuid import UUID

from boobiki.models import Device

logger = logging.getLogger(__name__)


class DeviceRegistry:
    def __init__(self) -> None:
        self._devices: dict[UUID, Device] = {}

    def add(self, device: Device) -> None:
        self._devices[device.id] = device
        logger.info("Device added: %s (%s)", device.name, device.id)

    def remove(self, device_id: UUID) -> None:
        device = self._devices.pop(device_id, None)
        if device:
            logger.info("Device removed: %s (%s)", device.name, device_id)

    def get(self, device_id: UUID) -> Device | None:
        return self._devices.get(device_id)

    def list_all(self) -> list[Device]:
        return list(self._devices.values())

    def update_last_seen(self, device_id: UUID) -> None:
        device = self._devices.get(device_id)
        if device:
            device.last_seen = datetime.now(tz=UTC)
