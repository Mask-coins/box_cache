"""A Windows cache with immutable historical bodies."""

from .cache import get, get_with_attributes, put
from .config import configure, load_config
from .exceptions import (
    CacheBusyError, CacheError, CacheWarning, CollisionError, ConfigurationError,
)

__all__ = [
    "get", "get_with_attributes", "put", "configure", "load_config", "CacheError", "CacheWarning",
    "CacheBusyError", "CollisionError", "ConfigurationError",
]

