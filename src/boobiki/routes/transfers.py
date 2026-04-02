import asyncio
import json
import logging
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from pywebpush import WebPushException, webpush

from boobiki.models import TransferMode, TransferStatus
from boobiki.push import PushStore
from boobiki.transfers import TransferManager
from boobiki.ws import ConnectionManager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


class TransferResponse(BaseModel):
    id: UUID
    filename: str
    size: int
    uploader_id: UUID
    mode: TransferMode
    status: TransferStatus
    created_at: datetime
    folder: str


class TransferPatchRequest(BaseModel):
    filename: str | None = None
    folder: str | None = None


class FolderCreateRequest(BaseModel):
    path: str


@router.post("/transfers", status_code=201)
async def create_transfer(
    request: Request,
    uploader_id: Annotated[UUID, Form()],
    file: UploadFile,
    mode: Annotated[TransferMode, Form()] = TransferMode.FAST_TRANSFER,
    folder: Annotated[str, Form()] = "/",
) -> TransferResponse:
    """Upload a file to fast transfer or storage."""
    manager: TransferManager = request.app.state.transfer_manager
    ws_manager: ConnectionManager = request.app.state.connection_manager

    content = await file.read()
    filename = file.filename or "unnamed"
    size = len(content)

    transfer = await manager.create(uploader_id, filename, size, mode, folder=folder)
    await manager.save_file(transfer.id, content)

    # Broadcast to ALL connected devices
    await ws_manager.broadcast({
        "type": "transfer_ready",
        "transfer_id": str(transfer.id),
        "filename": transfer.filename,
        "size": transfer.size,
        "uploader_id": str(transfer.uploader_id),
        "mode": transfer.mode,
    })

    return TransferResponse(
        id=transfer.id,
        filename=transfer.filename,
        size=transfer.size,
        uploader_id=transfer.uploader_id,
        mode=transfer.mode,
        status=transfer.status,
        created_at=transfer.created_at,
        folder=transfer.folder,
    )


@router.get("/transfers")
async def list_transfers(
    request: Request,
    mode: TransferMode | None = None,
    folder: str | None = None,
) -> list[TransferResponse]:
    """List all transfers, optionally filtered by mode."""
    manager: TransferManager = request.app.state.transfer_manager
    return [
        TransferResponse(
            id=t.id,
            filename=t.filename,
            size=t.size,
            uploader_id=t.uploader_id,
            mode=t.mode,
            status=t.status,
            created_at=t.created_at,
            folder=t.folder,
        )
        for t in manager.list_all(mode=mode, folder=folder)
    ]


@router.get("/transfers/{transfer_id}/download")
async def download_transfer(request: Request, transfer_id: UUID) -> StreamingResponse:
    """Download a transferred file."""
    manager: TransferManager = request.app.state.transfer_manager
    transfer = manager.get(transfer_id)
    if not transfer:
        raise HTTPException(status_code=404, detail="Transfer not found")

    await manager.mark_downloaded(transfer_id)
    return StreamingResponse(
        manager.get_file_stream(transfer_id),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{transfer.filename}"'},
    )


@router.patch("/transfers/{transfer_id}")
async def update_transfer(
    request: Request, transfer_id: UUID, body: TransferPatchRequest
) -> TransferResponse:
    manager: TransferManager = request.app.state.transfer_manager
    ws_manager: ConnectionManager = request.app.state.connection_manager

    transfer = manager.get(transfer_id)
    if not transfer:
        raise HTTPException(status_code=404, detail="Transfer not found")

    try:
        if body.filename is not None:
            transfer = await manager.rename(transfer_id, body.filename)
        if body.folder is not None:
            transfer = await manager.move_to_folder(transfer_id, body.folder)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    await ws_manager.broadcast(
        {"type": "transfer_updated", "transfer_id": str(transfer_id)}
    )

    return TransferResponse(
        id=transfer.id,
        filename=transfer.filename,
        size=transfer.size,
        uploader_id=transfer.uploader_id,
        mode=transfer.mode,
        status=transfer.status,
        created_at=transfer.created_at,
        folder=transfer.folder,
    )


@router.delete("/transfers/{transfer_id}", status_code=204)
async def delete_transfer(request: Request, transfer_id: UUID) -> None:
    """Manually delete a transfer."""
    manager: TransferManager = request.app.state.transfer_manager
    deleted = await manager.delete(transfer_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Transfer not found")


@router.post("/folders", status_code=201)
async def create_folder(request: Request, body: FolderCreateRequest) -> dict[str, str]:
    manager: TransferManager = request.app.state.transfer_manager
    try:
        normalized = manager.create_folder(body.path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"path": normalized}


@router.get("/folders")
async def list_folders(request: Request) -> list[str]:
    manager: TransferManager = request.app.state.transfer_manager
    return manager.list_folders()


@router.delete("/folders", status_code=204)
async def delete_folder(request: Request, path: str) -> None:
    manager: TransferManager = request.app.state.transfer_manager
    try:
        manager.delete_folder(path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


class ClipCreateRequest(BaseModel):
    text: str
    uploader_id: UUID


class ClipResponse(BaseModel):
    id: UUID
    text: str
    uploader_id: UUID
    uploader_name: str
    created_at: datetime


@router.post("/clips", status_code=201)
async def create_clip(request: Request, body: ClipCreateRequest) -> ClipResponse:
    """Share a text clip to the clipboard."""
    manager: TransferManager = request.app.state.transfer_manager
    ws_manager: ConnectionManager = request.app.state.connection_manager
    registry = request.app.state.device_registry

    sender = registry.get(body.uploader_id)
    sender_name = sender.name if sender else "Unknown"

    clip = manager.add_clip(body.text, body.uploader_id, uploader_name=sender_name)

    await ws_manager.broadcast({
        "type": "clip_added",
        "clip_id": str(clip.id),
        "text": clip.text[:100],
        "uploader_id": str(clip.uploader_id),
        "sender": sender_name,
    })

    return ClipResponse(
        id=clip.id,
        text=clip.text,
        uploader_id=clip.uploader_id,
        uploader_name=clip.uploader_name,
        created_at=clip.created_at,
    )


@router.get("/clips")
async def list_clips(request: Request) -> list[ClipResponse]:
    """List all shared clips, newest first."""
    manager: TransferManager = request.app.state.transfer_manager
    return [
        ClipResponse(
            id=c.id, text=c.text, uploader_id=c.uploader_id,
            uploader_name=c.uploader_name, created_at=c.created_at,
        )
        for c in manager.list_clips()
    ]


@router.delete("/clips/{clip_id}", status_code=204)
async def delete_clip(request: Request, clip_id: UUID) -> None:
    """Delete a clip."""
    manager: TransferManager = request.app.state.transfer_manager
    deleted = manager.delete_clip(clip_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Clip not found")


class NotificationRequest(BaseModel):
    text: str
    sender_device_id: UUID | None = None
    target_device_id: UUID | None = None  # None = broadcast to all


@router.post("/notifications", status_code=201)
async def send_notification(request: Request, body: NotificationRequest) -> dict[str, str]:
    """Send a notification to all devices or a specific device."""
    ws_manager: ConnectionManager = request.app.state.connection_manager
    registry = request.app.state.device_registry
    settings = request.app.state.settings

    sender_name = "Unknown"
    if body.sender_device_id:
        device = registry.get(body.sender_device_id)
        if device:
            sender_name = device.name

    message: dict[str, object] = {
        "type": "notification",
        "text": body.text,
        "sender": sender_name,
    }

    if body.target_device_id:
        await ws_manager.send_to(body.target_device_id, message)
    else:
        await ws_manager.broadcast(message)

    # Also send via Web Push for mobile/backgrounded devices
    push_store: PushStore = request.app.state.push_store
    target = str(body.target_device_id) if body.target_device_id else None
    push_text = f"{sender_name}: {body.text}"
    await asyncio.to_thread(
        _send_push, push_text, target, settings.vapid_private_key, settings.vapid_email,
        push_store,
    )

    return {"status": "sent"}


def _send_push(
    text: str,
    target_device_id: str | None,
    vapid_private_key: str,
    vapid_email: str,
    push_store: PushStore,
) -> None:
    subs = push_store.get_all()
    if target_device_id:
        sub = subs.get(target_device_id)
        targets = {target_device_id: sub} if sub else {}
    else:
        targets = dict(subs)

    payload = json.dumps({
        "title": "Boobiki",
        "body": text,
        "icon": "/static/icons/icon-192.png",
    })
    stale: list[str] = []

    for did, sub_info in targets.items():
        try:
            webpush(
                subscription_info=sub_info,
                data=payload,
                vapid_private_key=vapid_private_key,
                vapid_claims={"sub": f"mailto:{vapid_email}"},
                headers={"Urgency": "high", "TTL": "86400"},
            )
        except WebPushException as exc:
            logger.warning("Push failed for %s: %s", did, exc)
            if "410" in str(exc) or "404" in str(exc):
                stale.append(did)
        except Exception:
            logger.warning("Push failed for %s", did, exc_info=True)

    if stale:
        push_store.remove_stale(stale)
