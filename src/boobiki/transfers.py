import asyncio
import json
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

from boobiki.models import Clip, Transfer, TransferMode, TransferStatus

logger = logging.getLogger(__name__)

CHUNK_SIZE = 64 * 1024
STATE_FILENAME = "state.json"


class TransferManager:
    def __init__(self, fast_transfer_dir: Path, storage_dir: Path, ttl_hours: int) -> None:
        self._transfers: dict[UUID, Transfer] = {}
        self._folders: set[str] = {"/"}
        self._clips: list[Clip] = []
        self._fast_transfer_dir = fast_transfer_dir
        self._storage_dir = storage_dir
        self._ttl_hours = ttl_hours
        self._fast_transfer_dir.mkdir(parents=True, exist_ok=True)
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        self._load_state()

    def _base_dir(self, mode: TransferMode) -> Path:
        if mode == TransferMode.STORAGE:
            return self._storage_dir
        return self._fast_transfer_dir

    def _resolve_dir(self, mode: TransferMode, folder: str) -> Path:
        base = self._base_dir(mode)
        if folder == "/":
            return base
        return base / folder.lstrip("/")

    def _unique_filepath(self, directory: Path, filename: str) -> Path:
        target = directory / filename
        if not target.exists():
            return target
        stem = Path(filename).stem
        suffix = Path(filename).suffix
        counter = 1
        while True:
            candidate = directory / f"{stem}_{counter}{suffix}"
            if not candidate.exists():
                return candidate
            counter += 1

    # -- Persistence -----------------------------------------------------------

    def _state_file(self) -> Path:
        return self._storage_dir.parent / "boobiki_state.json"

    def _save_state(self) -> None:
        data = {
            "folders": sorted(self._folders),
            "transfers": [
                {
                    "id": str(t.id),
                    "filename": t.filename,
                    "size": t.size,
                    "uploader_id": str(t.uploader_id),
                    "mode": t.mode,
                    "status": t.status,
                    "created_at": t.created_at.isoformat(),
                    "file_path": t.file_path,
                    "folder": t.folder,
                }
                for t in self._transfers.values()
            ],
            "clips": [
                {
                    "id": str(c.id),
                    "text": c.text,
                    "uploader_id": str(c.uploader_id),
                    "created_at": c.created_at.isoformat(),
                }
                for c in self._clips
            ],
        }
        state_file = self._state_file()
        state_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _load_state(self) -> None:
        state_file = self._state_file()
        if not state_file.exists():
            return
        try:
            data = json.loads(state_file.read_text(encoding="utf-8"))
            for f in data.get("folders", []):
                self._folders.add(f)
            for t_data in data.get("transfers", []):
                file_path = t_data["file_path"]
                if not Path(file_path).exists():
                    continue
                transfer = Transfer(
                    id=UUID(t_data["id"]),
                    filename=t_data["filename"],
                    size=t_data["size"],
                    uploader_id=UUID(t_data["uploader_id"]),
                    mode=TransferMode(t_data["mode"]),
                    status=TransferStatus(t_data["status"]),
                    created_at=datetime.fromisoformat(t_data["created_at"]),
                    file_path=file_path,
                    folder=t_data.get("folder", "/"),
                )
                self._transfers[transfer.id] = transfer
            for c_data in data.get("clips", []):
                clip = Clip(
                    id=UUID(c_data["id"]),
                    text=c_data["text"],
                    uploader_id=UUID(c_data["uploader_id"]),
                    created_at=datetime.fromisoformat(c_data["created_at"]),
                )
                self._clips.append(clip)
            logger.info(
                "Loaded state: %d transfers, %d folders, %d clips",
                len(self._transfers),
                len(self._folders),
                len(self._clips),
            )
        except (json.JSONDecodeError, KeyError, ValueError):
            logger.warning("Failed to load state file, starting fresh")

    # -- Validation helpers ----------------------------------------------------

    @staticmethod
    def _sanitize_filename(name: str) -> str:
        name = name.strip()
        if not name:
            msg = "Filename cannot be empty"
            raise ValueError(msg)
        if any(c in name for c in '/\\<>:"|?*'):
            msg = "Filename contains invalid characters"
            raise ValueError(msg)
        if name in (".", ".."):
            msg = "Invalid filename"
            raise ValueError(msg)
        return name[:255]

    @staticmethod
    def _normalize_folder_path(raw: str) -> str:
        raw = raw.strip()
        if not raw or raw == "/":
            return "/"
        parts = [p for p in raw.split("/") if p and p != ".."]
        if not parts:
            return "/"
        return "/" + "/".join(parts)

    # -- Transfer CRUD ---------------------------------------------------------

    async def create(
        self, uploader_id: UUID, filename: str, size: int, mode: TransferMode, folder: str = "/"
    ) -> Transfer:
        transfer_id = uuid4()

        resolved_folder = "/"
        if mode == TransferMode.STORAGE:
            resolved_folder = self._normalize_folder_path(folder)
            if resolved_folder not in self._folders:
                msg = f"Folder not found: {resolved_folder}"
                raise ValueError(msg)

        target_dir = self._resolve_dir(mode, resolved_folder)
        await asyncio.to_thread(target_dir.mkdir, parents=True, exist_ok=True)

        file_path = await asyncio.to_thread(self._unique_filepath, target_dir, filename)
        actual_filename = file_path.name

        transfer = Transfer(
            id=transfer_id,
            filename=actual_filename,
            size=size,
            uploader_id=uploader_id,
            mode=mode,
            status=TransferStatus.READY,
            file_path=str(file_path),
            folder=resolved_folder,
        )
        self._transfers[transfer_id] = transfer
        return transfer

    async def save_file(self, transfer_id: UUID, content: bytes) -> None:
        transfer = self._transfers.get(transfer_id)
        if not transfer:
            msg = f"Transfer {transfer_id} not found"
            raise ValueError(msg)
        await asyncio.to_thread(Path(transfer.file_path).write_bytes, content)
        transfer.status = TransferStatus.READY
        self._save_state()
        logger.info(
            "File saved: %s (%d bytes) [%s]", transfer.filename, len(content), transfer.mode
        )

    async def get_file_stream(self, transfer_id: UUID) -> AsyncIterator[bytes]:
        transfer = self._transfers.get(transfer_id)
        if not transfer:
            msg = f"Transfer {transfer_id} not found"
            raise ValueError(msg)
        path = Path(transfer.file_path)

        def _read_chunks() -> list[bytes]:
            chunks: list[bytes] = []
            with open(path, "rb") as f:
                while True:
                    chunk = f.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    chunks.append(chunk)
            return chunks

        chunks = await asyncio.to_thread(_read_chunks)
        for chunk in chunks:
            yield chunk

    async def mark_downloaded(self, transfer_id: UUID) -> None:
        transfer = self._transfers.get(transfer_id)
        if transfer:
            transfer.status = TransferStatus.DOWNLOADED
            self._save_state()

    def get(self, transfer_id: UUID) -> Transfer | None:
        return self._transfers.get(transfer_id)

    def list_all(
        self, mode: TransferMode | None = None, folder: str | None = None
    ) -> list[Transfer]:
        result = list(self._transfers.values())
        if mode is not None:
            result = [t for t in result if t.mode == mode]
        if folder is not None:
            result = [t for t in result if t.folder == folder]
        return result

    async def delete(self, transfer_id: UUID) -> bool:
        transfer = self._transfers.get(transfer_id)
        if not transfer:
            return False
        file_path = Path(transfer.file_path)
        if await asyncio.to_thread(file_path.exists):
            await asyncio.to_thread(file_path.unlink)
        del self._transfers[transfer_id]
        self._save_state()
        logger.info("Deleted transfer: %s (%s)", transfer.filename, transfer.mode)
        return True

    async def cleanup_expired(self) -> int:
        cutoff = datetime.now(tz=UTC) - timedelta(hours=self._ttl_hours)
        expired = [
            t
            for t in self._transfers.values()
            if t.mode == TransferMode.FAST_TRANSFER
            and t.created_at < cutoff
            and t.status != TransferStatus.UPLOADING
        ]
        count = 0
        for transfer in expired:
            await self.delete(transfer.id)
            count += 1
        if count:
            logger.info("Cleaned up %d expired fast transfers", count)
        return count

    # -- Rename ----------------------------------------------------------------

    async def rename(self, transfer_id: UUID, new_filename: str) -> Transfer:
        transfer = self._transfers.get(transfer_id)
        if not transfer:
            msg = f"Transfer {transfer_id} not found"
            raise ValueError(msg)
        new_filename = self._sanitize_filename(new_filename)
        old_path = Path(transfer.file_path)
        new_path = old_path.parent / new_filename
        if new_path.exists() and new_path != old_path:
            new_path = self._unique_filepath(old_path.parent, new_filename)
            new_filename = new_path.name
        await asyncio.to_thread(old_path.rename, new_path)
        transfer.filename = new_filename
        transfer.file_path = str(new_path)
        self._save_state()
        logger.info("Renamed: %s -> %s", old_path.name, new_filename)
        return transfer

    # -- Folder management -----------------------------------------------------

    def create_folder(self, path: str) -> str:
        path = self._normalize_folder_path(path)
        if path in self._folders:
            msg = f"Folder already exists: {path}"
            raise ValueError(msg)
        if path != "/":
            parent = self._normalize_folder_path("/".join(path.split("/")[:-1]))
            if parent not in self._folders:
                msg = f"Parent folder does not exist: {parent}"
                raise ValueError(msg)
        self._folders.add(path)
        real_dir = self._storage_dir / path.lstrip("/")
        real_dir.mkdir(parents=True, exist_ok=True)
        self._save_state()
        logger.info("Created folder: %s", path)
        return path

    def delete_folder(self, path: str) -> bool:
        path = self._normalize_folder_path(path)
        if path == "/":
            msg = "Cannot delete root folder"
            raise ValueError(msg)
        if path not in self._folders:
            msg = f"Folder not found: {path}"
            raise ValueError(msg)
        if any(t.folder == path for t in self._transfers.values()):
            msg = f"Folder is not empty: {path}"
            raise ValueError(msg)
        if any(f.startswith(path + "/") for f in self._folders):
            msg = f"Folder has sub-folders: {path}"
            raise ValueError(msg)
        self._folders.discard(path)
        real_dir = self._storage_dir / path.lstrip("/")
        if real_dir.exists() and not any(real_dir.iterdir()):
            real_dir.rmdir()
        self._save_state()
        logger.info("Deleted folder: %s", path)
        return True

    def list_folders(self) -> list[str]:
        return sorted(self._folders)

    async def move_to_folder(self, transfer_id: UUID, folder_path: str) -> Transfer:
        transfer = self._transfers.get(transfer_id)
        if not transfer:
            msg = f"Transfer {transfer_id} not found"
            raise ValueError(msg)
        if transfer.mode != TransferMode.STORAGE:
            msg = "Can only move Storage files between folders"
            raise ValueError(msg)
        folder_path = self._normalize_folder_path(folder_path)
        if folder_path not in self._folders:
            msg = f"Folder not found: {folder_path}"
            raise ValueError(msg)

        old_path = Path(transfer.file_path)
        new_dir = self._resolve_dir(TransferMode.STORAGE, folder_path)
        await asyncio.to_thread(new_dir.mkdir, parents=True, exist_ok=True)
        new_path = await asyncio.to_thread(self._unique_filepath, new_dir, transfer.filename)
        await asyncio.to_thread(old_path.rename, new_path)

        transfer.folder = folder_path
        transfer.filename = new_path.name
        transfer.file_path = str(new_path)
        self._save_state()
        logger.info("Moved %s to folder %s", transfer.filename, folder_path)
        return transfer

    # -- Clipboard -------------------------------------------------------------

    def add_clip(self, text: str, uploader_id: UUID) -> Clip:
        """Add a text clip to the shared clipboard."""
        clip = Clip(text=text, uploader_id=uploader_id)
        self._clips.insert(0, clip)  # newest first
        # Keep max 50 clips
        if len(self._clips) > 50:
            self._clips = self._clips[:50]
        self._save_state()
        logger.info("Clip added: %d chars", len(text))
        return clip

    def list_clips(self) -> list[Clip]:
        """Return all clips, newest first."""
        return list(self._clips)

    def delete_clip(self, clip_id: UUID) -> bool:
        """Delete a clip by ID."""
        for i, clip in enumerate(self._clips):
            if clip.id == clip_id:
                self._clips.pop(i)
                self._save_state()
                return True
        return False
