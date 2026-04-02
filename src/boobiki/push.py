import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class PushStore:
    def __init__(self, data_dir: Path) -> None:
        self._file = data_dir / "push_subscriptions.json"
        self._subscriptions: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if self._file.exists():
            try:
                self._subscriptions = json.loads(self._file.read_text(encoding="utf-8"))
                logger.info("Loaded %d push subscriptions", len(self._subscriptions))
            except (json.JSONDecodeError, ValueError):
                logger.warning("Failed to load push subscriptions, starting fresh")

    def _save(self) -> None:
        self._file.parent.mkdir(parents=True, exist_ok=True)
        self._file.write_text(json.dumps(self._subscriptions), encoding="utf-8")

    def subscribe(self, device_id: str, subscription: dict[str, Any]) -> None:
        self._subscriptions[device_id] = subscription
        self._save()

    def unsubscribe(self, device_id: str) -> None:
        if self._subscriptions.pop(device_id, None) is not None:
            self._save()

    def get_all(self) -> dict[str, dict[str, Any]]:
        return self._subscriptions

    def get(self, device_id: str) -> dict[str, Any] | None:
        return self._subscriptions.get(device_id)

    def remove_stale(self, device_ids: list[str]) -> None:
        changed = False
        for did in device_ids:
            if self._subscriptions.pop(did, None) is not None:
                changed = True
        if changed:
            self._save()
