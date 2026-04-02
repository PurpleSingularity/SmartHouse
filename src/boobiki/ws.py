import logging
from uuid import UUID, uuid4

from starlette.websockets import WebSocket

from boobiki.devices import DeviceRegistry
from boobiki.models import Device, DeviceType

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self, registry: DeviceRegistry) -> None:
        self._connections: dict[UUID, WebSocket] = {}
        self._registry = registry

    async def connect(self, ws: WebSocket, device_name: str) -> UUID:
        """Accept WebSocket, register device, broadcast join. Returns device_id."""
        await ws.accept()
        device_id = uuid4()
        client = ws.scope.get("client")
        ip = client[0] if client else ""
        device = Device(
            id=device_id,
            name=device_name,
            device_type=DeviceType.BROWSER,
            ip=ip,
        )
        self._connections[device_id] = ws
        self._registry.add(device)
        await self.broadcast(
            {"type": "device_joined", "device_id": str(device_id), "name": device_name},
            exclude=device_id,
        )
        return device_id

    async def disconnect(self, device_id: UUID) -> None:
        """Remove connection and mark device offline, broadcast leave."""
        self._connections.pop(device_id, None)
        device = self._registry.get(device_id)
        name = device.name if device else "unknown"
        self._registry.mark_offline(device_id)
        await self.broadcast(
            {"type": "device_left", "device_id": str(device_id), "name": name},
        )

    async def reconnect(self, ws: WebSocket, device_id: UUID, device_name: str) -> UUID:
        """Reconnect an existing device. Returns device_id."""
        self._connections[device_id] = ws
        device = self._registry.get(device_id)
        if device:
            device.name = device_name
            self._registry.mark_online(device_id)
        else:
            # Device was cleaned up, re-add
            client = ws.scope.get("client")
            ip = client[0] if client else ""
            new_device = Device(
                id=device_id, name=device_name, device_type=DeviceType.BROWSER, ip=ip
            )
            self._registry.add(new_device)
        await self.broadcast(
            {"type": "device_joined", "device_id": str(device_id), "name": device_name},
            exclude=device_id,
        )
        return device_id

    async def send_to(self, device_id: UUID, message: dict[str, object]) -> None:
        """Send JSON message to a specific device."""
        ws = self._connections.get(device_id)
        if ws:
            await ws.send_json(message)

    async def broadcast(
        self, message: dict[str, object], exclude: UUID | None = None
    ) -> None:
        """Broadcast JSON message to all connected devices, optionally excluding one."""
        for did, ws in self._connections.items():
            if did != exclude:
                try:
                    await ws.send_json(message)
                except Exception:
                    logger.warning("Failed to send to device %s", did)
