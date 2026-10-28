"""Version-preserving public cache operations."""

import json
from pathlib import Path

from . import metadata
from .config import load_config
from .exceptions import CacheError, CollisionError
from .metadata import JSONValue
from .storage import (
    is_reparse, json_bytes, locked, publish, replace_owned_json, report, temporary,
)


def _versions(directory: Path, project: str, digest: str) -> list[tuple[str, Path]]:
    versions = []
    seen = set()
    for path in directory.iterdir():
        match = metadata.FILE_PATTERN.fullmatch(path.name)
        if not match or match["digest"] != digest:
            continue
        existing = match["project"]
        if existing.casefold() != project.casefold():
            continue
        if existing != project:
            raise CollisionError(
                f"Project spelling conflicts: {project!r} vs {existing!r} ({path})"
            )
        stem = path.stem
        if stem not in seen:
            versions.append((match["stamp"], directory / stem))
            seen.add(stem)
    return versions


def put(project: str, key: str, data: bytes | str, *,
        attributes: dict[str, JSONValue] | None = None) -> None:
    """Append a version with optional JSON attributes; never overwrite history."""
    metadata.validate_project(project)
    digest = metadata.key_hash(key)
    body, kind = metadata.encode(data)
    saved_attributes = metadata.copy_attributes(attributes)
    directory = Path(load_config()["cache_dir"])
    try:
        with locked(directory):
            _versions(directory, project, digest)  # Also checks spelling conflicts.
            saved = metadata.now()
            stamp = metadata.timestamp(saved)
            base = directory / f"{project}_{digest}_{stamp}"
            data_path = Path(str(base) + ".data")
            meta_path = Path(str(base) + ".json")
            if data_path.exists() or meta_path.exists():
                raise CollisionError(f"Cache timestamp collision: {base}")
            value = metadata.make_metadata(project, key, body, kind, saved, saved_attributes)
            body_temp = temporary(directory, body)
            meta_temp = temporary(directory, json_bytes(value))
            publish(body_temp, data_path)
            publish(meta_temp, meta_path)  # Commit marker, always published last.
    except (OSError, CacheError) as exc:
        report(directory, f"Cache save stopped for {project!r}/{key!r}: {exc}")
        if isinstance(exc, CacheError):
            raise
        raise CacheError(str(exc)) from exc


def _corrupt(directory: Path, path: Path, reason: str, value: dict | None) -> None:
    if value is not None:
        # Preserve original fields and body; record detection separately.
        previous = value.get("corruption")
        if not isinstance(previous, dict) or previous.get("reason") != reason:
            value["corruption"] = {
                "detected_at": metadata.now().isoformat(timespec="milliseconds"),
                "reason": reason,
            }
            try:
                replace_owned_json(path, value)
            except (OSError, CacheError) as exc:
                report(directory, f"Cannot record corruption in {path}: {exc}")
    report(directory, f"Corrupt cache {path}: {reason}")


def get(project: str, key: str) -> bytes | str | None:
    """Return the newest saved version, or None for a missing/corrupt cache."""
    result = get_with_attributes(project, key)
    return None if result is None else result[0]


def get_with_attributes(
    project: str, key: str,
) -> tuple[bytes | str, dict[str, JSONValue]] | None:
    """Return (body, user attributes) from one newest version under one lock.

    Old versions without attributes return an empty dictionary. Management fields
    such as saved_at and sha256 are not exposed through this dictionary.
    """
    metadata.validate_project(project)
    digest = metadata.key_hash(key)
    directory = Path(load_config()["cache_dir"])
    try:
        with locked(directory):
            versions = _versions(directory, project, digest)
            if not versions:
                return None
            stamp, base = max(versions, key=lambda item: item[0])
            meta_path = Path(str(base) + ".json")
            body_path = Path(str(base) + ".data")
            value = None
            try:
                if meta_path.exists() and is_reparse(meta_path):
                    raise ValueError("Metadata is a reparse point")
                try:
                    raw = json.loads(meta_path.read_text(encoding="utf-8"))
                except FileNotFoundError as exc:
                    raise ValueError("Metadata missing or save was interrupted") from exc
                value = metadata.validate_metadata(raw, project, key, stamp)
                if body_path.exists() and is_reparse(body_path):
                    raise ValueError("Cache body is a reparse point")
                try:
                    body = body_path.read_bytes()
                except FileNotFoundError as exc:
                    raise ValueError("Cache body is missing") from exc
                return metadata.decode(body, value), value.get("attributes", {})
            except (ValueError, UnicodeError, RecursionError) as exc:
                _corrupt(directory, meta_path, str(exc), value)
                return None
    except (OSError, CacheError) as exc:
        report(directory, f"Cache read stopped for {project!r}/{key!r}: {exc}")
        if isinstance(exc, CacheError):
            raise
        raise CacheError(str(exc)) from exc

