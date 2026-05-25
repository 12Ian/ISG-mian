from __future__ import annotations

import hashlib
import mimetypes
import shutil
from pathlib import Path


class FileIndexer:
    def copy_into_dataset(self, source_path: Path, target_root: Path, relative_path: str | None = None) -> Path:
        relative = Path(relative_path or source_path.name)
        destination = target_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        stem = destination.stem
        suffix = destination.suffix
        counter = 1
        while destination.exists():
            destination = destination.with_name(f"{stem}_{counter}{suffix}")
            counter += 1
        shutil.copy2(source_path, destination)
        return destination

    def compute_sha256(self, file_path: Path) -> str:
        digest = hashlib.sha256()
        with file_path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(65536), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def detect_mime_type(self, file_path: Path) -> str:
        mime_type, _ = mimetypes.guess_type(file_path.name)
        return mime_type or "application/octet-stream"
