from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from boobiki.devices import DeviceRegistry
from boobiki.models import DeviceType
from boobiki.ws import ConnectionManager

router = APIRouter(prefix="/api")


class DeviceResponse(BaseModel):
    id: UUID
    name: str
    device_type: DeviceType
    ip: str
    port: int
    last_seen: datetime
    online: bool


class DeviceRenameRequest(BaseModel):
    name: str


@router.get("/devices")
async def list_devices(request: Request) -> list[DeviceResponse]:
    registry: DeviceRegistry = request.app.state.device_registry
    return [
        DeviceResponse(
            id=d.id,
            name=d.name,
            device_type=d.device_type,
            ip=d.ip,
            port=d.port,
            last_seen=d.last_seen,
            online=d.online,
        )
        for d in registry.list_all()
    ]


@router.patch("/devices/{device_id}")
async def rename_device(
    request: Request, device_id: UUID, body: DeviceRenameRequest
) -> DeviceResponse:
    registry: DeviceRegistry = request.app.state.device_registry
    device = registry.rename(device_id, body.name)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    ws_manager: ConnectionManager = request.app.state.connection_manager
    await ws_manager.broadcast({
        "type": "device_renamed",
        "device_id": str(device_id),
        "name": body.name,
    })
    return DeviceResponse(
        id=device.id,
        name=device.name,
        device_type=device.device_type,
        ip=device.ip,
        port=device.port,
        last_seen=device.last_seen,
        online=device.online,
    )


@router.delete("/devices/{device_id}", status_code=204)
async def delete_device(request: Request, device_id: UUID) -> None:
    registry: DeviceRegistry = request.app.state.device_registry
    device = registry.get(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    ws_manager: ConnectionManager = request.app.state.connection_manager
    # Close WS if connected, then remove entirely
    ws = ws_manager._connections.pop(device_id, None)  # noqa: SLF001
    if ws:
        await ws.close()
    registry.remove(device_id)
    await ws_manager.broadcast({
        "type": "device_left", "device_id": str(device_id), "name": device.name,
    })
