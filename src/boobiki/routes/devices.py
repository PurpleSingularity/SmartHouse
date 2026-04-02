from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import BaseModel

from boobiki.devices import DeviceRegistry
from boobiki.models import DeviceType

router = APIRouter(prefix="/api")


class DeviceResponse(BaseModel):
    id: UUID
    name: str
    device_type: DeviceType
    ip: str
    port: int
    last_seen: datetime


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
        )
        for d in registry.list_all()
    ]
