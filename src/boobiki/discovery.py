import asyncio
import logging
import socket
from uuid import UUID, uuid4

from zeroconf import ServiceInfo, ServiceStateChange, Zeroconf
from zeroconf.asyncio import AsyncServiceBrowser, AsyncServiceInfo, AsyncZeroconf

from boobiki.devices import DeviceRegistry
from boobiki.models import Device, DeviceType

logger = logging.getLogger(__name__)


def get_local_ip() -> str:
    """Get the local LAN IP address."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            ip: str = s.getsockname()[0]
            return ip
    except OSError:
        return "127.0.0.1"


class BoobikiServiceHandler:
    """Handles mDNS service events, updates DeviceRegistry via async tasks."""

    def __init__(self, registry: DeviceRegistry, azc: AsyncZeroconf, own_id: str) -> None:
        self._registry = registry
        self._azc = azc
        self._own_id = own_id
        self._discovered: dict[str, UUID] = {}

    def on_service_state_change(
        self,
        zeroconf: Zeroconf,
        service_type: str,
        name: str,
        state_change: ServiceStateChange,
    ) -> None:
        if state_change == ServiceStateChange.Added:
            asyncio.ensure_future(self._handle_added(service_type, name))
        elif state_change == ServiceStateChange.Removed and name in self._discovered:
                device_id = self._discovered.pop(name)
                self._registry.remove(device_id)
                logger.info("Server removed: %s", name)

    async def _handle_added(self, service_type: str, name: str) -> None:
        info = AsyncServiceInfo(service_type, name)
        got_info = await info.async_request(self._azc.zeroconf, 3000)
        if got_info and info.properties and info.port is not None:
                raw_id = info.properties.get(b"device_id", b"")
                device_id_str = raw_id.decode() if raw_id else ""
                if device_id_str == self._own_id:
                    return
                raw_name = info.properties.get(b"device_name", b"unknown")
                device_name = raw_name.decode() if raw_name else "unknown"
                addresses = info.parsed_addresses()
                ip = addresses[0] if addresses else ""
                device_id = uuid4()
                self._discovered[name] = device_id
                device = Device(
                    id=device_id,
                    name=device_name,
                    device_type=DeviceType.SERVER,
                    ip=ip,
                    port=info.port,
                )
                self._registry.add(device)
                logger.info("Discovered server: %s at %s:%d", device_name, ip, info.port)


class DiscoveryService:
    """Manages Zeroconf service registration and browsing."""

    def __init__(
        self, registry: DeviceRegistry, service_type: str, device_name: str, port: int
    ) -> None:
        self._registry = registry
        self._service_type = service_type
        self._device_name = device_name
        self._port = port
        self._device_id = str(uuid4())
        self._azc: AsyncZeroconf | None = None
        self._browser: AsyncServiceBrowser | None = None
        self._info: ServiceInfo | None = None

    async def start(self) -> None:
        """Register mDNS service and start browsing for peers."""
        local_ip = get_local_ip()

        self._azc = AsyncZeroconf()
        self._info = ServiceInfo(
            self._service_type,
            f"{self._device_name}.{self._service_type}",
            addresses=[socket.inet_aton(local_ip)],
            port=self._port,
            properties={
                "device_id": self._device_id,
                "device_name": self._device_name,
            },
        )
        await self._azc.async_register_service(self._info, allow_name_change=True)
        logger.info(
            "Registered mDNS service: %s at %s:%d", self._device_name, local_ip, self._port
        )
        print(f"\n  Connect from other devices: http://{local_ip}:{self._port}\n")

        handler = BoobikiServiceHandler(self._registry, self._azc, own_id=self._device_id)
        self._browser = AsyncServiceBrowser(
            self._azc.zeroconf, self._service_type, handlers=[handler.on_service_state_change]
        )

    async def stop(self) -> None:
        """Unregister service and stop browsing."""
        if self._browser:
            await self._browser.async_cancel()
        if self._azc and self._info:
            await self._azc.async_unregister_service(self._info)
        if self._azc:
            await self._azc.async_close()
        logger.info("Discovery service stopped")
