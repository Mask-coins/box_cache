"""Public errors and warnings."""

import warnings


class CacheWarning(UserWarning):
    """A problem that should be visible to the caller."""


class CacheError(RuntimeError):
    """An operation stopped without silently changing its destination."""


class ConfigurationError(CacheError):
    """Missing, foreign, or unusable configuration or cache directory."""


class CollisionError(CacheError):
    """A filename or project spelling conflicts with existing evidence."""


class CacheBusyError(CacheError):
    """Another operation currently holds the cache lock."""


def warn(message: str) -> None:
    warnings.warn(message, CacheWarning, stacklevel=3)

