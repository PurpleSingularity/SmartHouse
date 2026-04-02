from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

from boobiki.push import PushStore

router = APIRouter(prefix="/api/push")


class SubscribeRequest(BaseModel):
    device_id: str
    subscription: dict[str, Any]


@router.get("/vapid-key")
async def vapid_key(request: Request) -> dict[str, str]:
    return {"public_key": request.app.state.settings.vapid_public_key}


@router.post("/subscribe", status_code=201)
async def subscribe(request: Request, body: SubscribeRequest) -> dict[str, str]:
    push_store: PushStore = request.app.state.push_store
    push_store.subscribe(body.device_id, body.subscription)
    return {"status": "subscribed"}
