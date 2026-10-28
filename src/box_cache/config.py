"""One user configuration shared by working directories and virtualenvs."""

import json
import os
from pathlib import Path

from .exceptions import CacheError, ConfigurationError, warn
from .metadata import reserved_component
from .storage import (
    MARKER_NAME, OWNER, is_reparse, json_bytes, publish,
    replace_owned_json, require_windows, temporary,
)


def config_path() -> Path:
    require_windows()
    root = os.environ.get("LOCALAPPDATA")
    if not root or not Path(root).is_absolute():
        raise ConfigurationError("LOCALAPPDATA must be an absolute path.")
    return Path(root) / "box_cache" / "config.json"


def _read(path: Path) -> dict:
    if is_reparse(path):
        raise ConfigurationError(f"Refusing a reparse point: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ConfigurationError(f"Cannot read configuration/marker: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ConfigurationError(f"Expected a JSON object: {path}")
    return value


def _settings(path: Path) -> dict:
    if not path.parent.is_dir() or is_reparse(path.parent):
        raise ConfigurationError(f"Invalid configuration directory: {path.parent}")
    value = _read(path)
    if (value.get("application") != "box_cache"
            or type(value.get("config_version")) is not int
            or value["config_version"] != 1
            or not isinstance(value.get("cache_dir"), str)
            or not Path(value["cache_dir"]).is_absolute()):
        raise ConfigurationError(f"Foreign or unsupported configuration: {path}")
    return value


def _validate_directory(directory: Path) -> None:
    if not directory.is_dir() or is_reparse(directory):
        raise ConfigurationError(f"Invalid cache directory: {directory}")
    marker = _read(directory / MARKER_NAME)
    if marker != OWNER or type(marker.get("format_version")) is not int:
        raise ConfigurationError(f"Foreign or unsupported cache directory: {directory}")


def load_config() -> dict:
    """Read and validate; no fallback and no implicit initialization."""
    try:
        path = config_path()
        value = _settings(path)
        directory = Path(value["cache_dir"])
        _separate(directory, path.parent)
        _validate_directory(directory)
        return value
    except (OSError, ValueError, CacheError) as exc:
        warn(str(exc))
        if isinstance(exc, ConfigurationError):
            raise
        raise ConfigurationError(str(exc)) from exc


def _separate(directory: Path, config_directory: Path) -> None:
    cache = directory.resolve()
    config = config_directory.resolve()
    if cache == config or cache in config.parents or config in cache.parents:
        raise ConfigurationError("Cache and configuration directories must not overlap.")


def configure(cache_dir: str | os.PathLike) -> Path:
    """Create owned directories, or update an already-owned configuration."""
    try:
        path = config_path()
        if path.parent.exists():
            _settings(path)  # An existing unmarked directory is never adopted.
        raw = os.fspath(cache_dir)
        if not isinstance(raw, str) or not raw.strip():
            raise ConfigurationError("Cache path must not be empty.")
        directory = Path(raw).absolute()
        # Reject invalid components before resolving or creating anything.
        for component in directory.parts[1:]:
            if component in (".", ".."):
                continue
            if (reserved_component(component)
                    or any(ord(char) < 32 or char in '<>:"|?*' for char in component)):
                raise ConfigurationError(f"Invalid cache path: {directory}")
        _separate(directory, path.parent)
        if directory.exists():
            _validate_directory(directory)
        else:
            # Requiring the parent to exist avoids creating a chain from a typo.
            directory.mkdir()
            publish(temporary(directory, json_bytes(OWNER)), directory / MARKER_NAME)
        value = {"application": "box_cache", "config_version": 1,
                 "cache_dir": str(directory.resolve())}
        if not path.parent.exists():
            path.parent.mkdir()
            publish(temporary(path.parent, json_bytes(value)), path)
        else:
            # Recheck immediately before modifying the owned configuration.
            _settings(path)
            replace_owned_json(path, value)
        return Path(value["cache_dir"])
    except (OSError, ValueError, CacheError) as exc:
        warn(str(exc))
        if isinstance(exc, ConfigurationError):
            raise
        raise ConfigurationError(str(exc)) from exc

