"""Local filesystem storage for uploaded originals.

Files are stored under a configurable directory using opaque UUID names to avoid
collisions and path traversal from user-supplied filenames. The download
endpoint streams them back using the original filename for display.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from app.core.config import get_settings


class FileStorage:
    """Persist and retrieve uploaded files on the local filesystem."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self._base_dir = base_dir or get_settings().storage_dir
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def save(self, data: bytes, *, extension: str) -> str:
        """Write ``data`` to a new file and return its relative storage key."""
        suffix = f".{extension.lstrip('.')}" if extension else ""
        key = f"{uuid.uuid4().hex}{suffix}"
        path = self._base_dir / key
        path.write_bytes(data)
        return key

    def resolve(self, key: str) -> Path:
        """Return the absolute path for a storage key."""
        return self._base_dir / key

    def read(self, key: str) -> bytes:
        """Read the bytes for a storage key."""
        return self.resolve(key).read_bytes()

    def delete(self, key: str) -> None:
        """Delete a stored file, ignoring an already-missing file."""
        self.resolve(key).unlink(missing_ok=True)
