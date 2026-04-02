import asyncio
import logging
import socket
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from boobiki.config import Settings, load_or_generate_vapid
from boobiki.devices import DeviceRegistry
from boobiki.discovery import DiscoveryService
from boobiki.push import PushStore
from boobiki.routes.devices import router as devices_router
from boobiki.routes.health import router as health_router
from boobiki.routes.push import router as push_router
from boobiki.routes.transfers import router as transfers_router
from boobiki.routes.ws import router as ws_router
from boobiki.transfers import TransferManager
from boobiki.ws import ConnectionManager

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = Settings()
    if not settings.device_name:
        settings.device_name = socket.gethostname()
    if not settings.vapid_private_key or not settings.vapid_public_key:
        priv, pub = load_or_generate_vapid(settings.data_dir)
        settings.vapid_private_key = priv
        settings.vapid_public_key = pub
    app.state.settings = settings

    push_store = PushStore(data_dir=Path(settings.data_dir))
    app.state.push_store = push_store

    registry = DeviceRegistry()
    app.state.device_registry = registry

    app.state.connection_manager = ConnectionManager(registry)

    transfer_manager = TransferManager(
        fast_transfer_dir=Path(settings.fast_transfer_dir),
        storage_dir=Path(settings.storage_dir),
        ttl_hours=settings.fast_transfer_ttl_hours,
    )
    app.state.transfer_manager = transfer_manager

    discovery = DiscoveryService(
        registry, settings.mdns_service_type, settings.device_name, settings.port
    )
    await discovery.start()
    app.state.discovery = discovery

    # Background cleanup task for expired transfers
    async def _cleanup_loop() -> None:
        while True:
            await asyncio.sleep(3600)  # every hour
            await transfer_manager.cleanup_expired()
            registry.cleanup_stale(max_offline_hours=24)

    cleanup_task = asyncio.create_task(_cleanup_loop())

    yield

    cleanup_task.cancel()
    await discovery.stop()


def create_app() -> FastAPI:
    from boobiki.logging_config import setup_logging

    setup_logging()

    app = FastAPI(title="Boobiki", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory="static"), name="static")
    app.include_router(health_router)
    app.include_router(devices_router)
    app.include_router(transfers_router)
    app.include_router(push_router)
    app.include_router(ws_router)

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse("static/index.html")

    @app.get("/sw.js")
    async def service_worker() -> FileResponse:
        return FileResponse("static/sw.js", media_type="application/javascript")

    return app


def main() -> None:
    settings = Settings()
    uvicorn.run(
        "boobiki.app:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
    )
