from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum, unique
from uuid import UUID, uuid4


@unique
class DeviceType(StrEnum):
    SERVER = "server"
    BROWSER = "browser"


@dataclass(slots=True)
class Device:
    id: UUID = field(default_factory=uuid4)
    name: str = ""
    device_type: DeviceType = DeviceType.BROWSER
    ip: str = ""
    port: int = 0
    last_seen: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
    online: bool = True


@unique
class TransferStatus(StrEnum):
    PENDING = "pending"
    UPLOADING = "uploading"
    READY = "ready"
    DOWNLOADED = "downloaded"
    EXPIRED = "expired"


@unique
class TransferMode(StrEnum):
    FAST_TRANSFER = "fast_transfer"
    STORAGE = "storage"


@dataclass(slots=True)
class Transfer:
    id: UUID = field(default_factory=uuid4)
    filename: str = ""
    size: int = 0
    uploader_id: UUID = field(default_factory=uuid4)
    mode: TransferMode = TransferMode.FAST_TRANSFER
    status: TransferStatus = TransferStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
    file_path: str = ""
    folder: str = "/"


@dataclass(slots=True)
class Clip:
    id: UUID = field(default_factory=uuid4)
    text: str = ""
    uploader_id: UUID = field(default_factory=uuid4)
    uploader_name: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
