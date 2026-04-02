import contextlib
import logging
from uuid import UUID, uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from boobiki.models import Device, DeviceType
from boobiki.ws import ConnectionManager

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    manager: ConnectionManager = ws.app.state.connection_manager

    await ws.accept()
    try:
        data = await ws.receive_json()
    except WebSocketDisconnect:
        return

    if not isinstance(data, dict) or data.get("type") != "register":
        await ws.close(code=1008, reason="Expected register message")
        return

    device_name = str(data.get("name", "Unknown Device"))

    # Bypass manager.connect() which calls accept() again.
    # Build the Device ourselves and register directly.
    raw_id = data.get("device_id")
    device_id: UUID | None = None
    if raw_id:
        with contextlib.suppress(ValueError):
            device_id = UUID(str(raw_id))

    if device_id:
        # Reconnecting existing device
        manager._connections[device_id] = ws  # noqa: SLF001
        existing = manager._registry.get(device_id)  # noqa: SLF001
        if existing:
            existing.name = device_name
            manager._registry.mark_online(device_id)  # noqa: SLF001
        else:
            client = ws.scope.get("client")
            ip = client[0] if client else ""
            device = Device(
                id=device_id, name=device_name, device_type=DeviceType.BROWSER, ip=ip
            )
            manager._registry.add(device)  # noqa: SLF001
        await manager.broadcast(
            {"type": "device_joined", "device_id": str(device_id), "name": device_name},
            exclude=device_id,
        )
    else:
        # New device
        device_id = uuid4()
        client = ws.scope.get("client")
        ip = client[0] if client else ""
        device = Device(
            id=device_id, name=device_name, device_type=DeviceType.BROWSER, ip=ip
        )
        manager._connections[device_id] = ws  # noqa: SLF001
        manager._registry.add(device)  # noqa: SLF001
        await manager.broadcast(
            {"type": "device_joined", "device_id": str(device_id), "name": device_name},
            exclude=device_id,
        )

    await ws.send_json({"type": "registered", "device_id": str(device_id)})

    try:
        while True:
            msg = await ws.receive_json()
            if isinstance(msg, dict) and msg.get("type") == "ping":
                await ws.send_json({"type": "pong"})
                manager._registry.update_last_seen(device_id)  # noqa: SLF001
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(device_id)
