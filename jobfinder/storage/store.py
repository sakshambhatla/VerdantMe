from __future__ import annotations

import json
import tempfile
from pathlib import Path


class JsonStorageBackend:
    """Local-filesystem storage backend using JSON files.

    Satisfies the :class:`~jobfinder.storage.backend.StorageBackend` protocol.
    """

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def read(self, filename: str) -> dict | list | None:
        path = self.data_dir / filename
        if not path.exists():
            return None
        with open(path) as f:
            return json.load(f)

    def write(self, filename: str, data: dict | list) -> None:
        path = self.data_dir / filename
        with tempfile.NamedTemporaryFile(
            mode="w", dir=self.data_dir, suffix=".tmp", delete=False
        ) as tmp:
            json.dump(data, tmp, indent=2, default=str)
            tmp_path = Path(tmp.name)
        tmp_path.rename(path)

    def exists(self, filename: str) -> bool:
        return (self.data_dir / filename).exists()

    def delete(self, filename: str) -> None:
        (self.data_dir / filename).unlink(missing_ok=True)


# Backward-compatible alias — existing code imports ``StorageManager``.
StorageManager = JsonStorageBackend
