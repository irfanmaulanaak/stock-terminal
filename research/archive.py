"""Safe JSON persistence and integrity manifests for snapshot archives."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Iterable

MANIFEST_VERSION = 1
DEFAULT_MANIFEST_NAME = "manifest.json"


def atomic_write_json(path: str | os.PathLike[str], value: Any) -> None:
    """Durably replace *path* with deterministic UTF-8 JSON."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
        directory_fd = os.open(destination.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def _digest(path: Path) -> str:
    checksum = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def generate_manifest(directory: str | os.PathLike[str], files: Iterable[str | os.PathLike[str]] | None = None) -> dict[str, Any]:
    """Build a deterministic manifest without modifying the archive directory."""
    root = Path(directory).resolve()
    candidates = sorted(files if files is not None else (p.relative_to(root) for p in root.rglob("*.json") if p.name != DEFAULT_MANIFEST_NAME), key=lambda p: str(p))
    entries = []
    for item in candidates:
        relative = Path(item)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"manifest path must stay inside archive: {item}")
        path = (root / relative).resolve()
        if root not in path.parents or not path.is_file():
            raise ValueError(f"manifest file is missing or outside archive: {item}")
        entries.append({"path": relative.as_posix(), "sha256": _digest(path), "bytes": path.stat().st_size})
    return {"manifest_version": MANIFEST_VERSION, "algorithm": "sha256", "files": entries}


def validate_manifest(directory: str | os.PathLike[str], manifest: Any) -> None:
    """Raise ValueError when manifest structure or archive contents differ."""
    if not isinstance(manifest, dict) or manifest.get("manifest_version") != MANIFEST_VERSION or manifest.get("algorithm") != "sha256":
        raise ValueError("unsupported or malformed manifest")
    entries = manifest.get("files")
    if not isinstance(entries, list):
        raise ValueError("manifest files must be an array")
    expected = generate_manifest(directory, [entry.get("path", "") for entry in entries if isinstance(entry, dict)])
    if expected != manifest:
        raise ValueError("archive does not match manifest")
