"""Windows filesystem primitives; never overwrite a published cache body."""

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import stat
import uuid

from .exceptions import CacheBusyError, CacheError, CollisionError, warn

MARKER_NAME = ".box_cache.json"
LOG_NAME = "box_cache.log"
OWNER = {"application": "box_cache", "format_version": 1}


def require_windows() -> None:
    if os.name != "nt":
        raise CacheError("box_cache supports Windows only.")


def is_reparse(path: Path) -> bool:
    return bool(path.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def json_bytes(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=True, indent=2) + "\n").encode("utf-8")


def temporary(directory: Path, data: bytes) -> Path:
    path = directory / f".box_cache-{uuid.uuid4().hex}.tmp"
    # Exclusive creation also protects temporary filenames.
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    return path


def publish(source: Path, destination: Path) -> None:
    require_windows()
    # On Windows rename fails if the destination exists; never use replace here.
    try:
        os.rename(source, destination)
    except FileExistsError as exc:
        raise CollisionError(f"Cache filename already exists: {destination}") from exc


def replace_owned_json(path: Path, value: dict) -> None:
    """Only for our validated configuration or a readable metadata record."""
    if path.exists() and is_reparse(path):
        raise CacheError(f"Refusing to replace a reparse point: {path}")
    temp = temporary(path.parent, json_bytes(value))
    os.replace(temp, path)


def report(directory: Path, message: str) -> None:
    """Append a single escaped JSON line and emit a Python warning."""
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "level": "WARNING",
        "message": message,
    }
    log = directory / LOG_NAME
    try:
        if log.exists() and is_reparse(log):
            raise OSError(f"Log is a reparse point: {log}")
        with log.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=True) + "\n")
    except OSError as exc:
        warn(f"Cannot write cache log {log}: {exc}")
    warn(message)


@contextmanager
def locked(directory: Path):
    """Nonblocking OS lock; Windows releases it when the process exits."""
    require_windows()
    import msvcrt

    marker = directory / MARKER_NAME
    if is_reparse(marker):
        raise CacheError(f"Cache marker is a reparse point: {marker}")
    with marker.open("r+b") as stream:
        # Lock beyond the JSON data so configuration validation remains readable.
        stream.seek(4096)
        try:
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            raise CacheBusyError(f"Cache is in use: {directory}") from exc
        try:
            yield
        finally:
            stream.seek(4096)
            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)

