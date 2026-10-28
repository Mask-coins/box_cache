"""Stable names, serialization, and integrity checks."""

from datetime import datetime, timezone
import hashlib
import re

FILE_PATTERN = re.compile(
    r"(?P<project>.+)_(?P<digest>[0-9a-f]{64})_"
    r"(?P<stamp>[0-9]{8}T[0-9]{9}Z)\.(?P<extension>json|data)\Z"
)
RESERVED = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"} | {
    f"{prefix}{number}" for prefix in ("COM", "LPT")
    for number in (*"123456789", "¹", "²", "³")
}


def reserved_component(value: str) -> bool:
    return (value.endswith((" ", "."))
            or value.split(".", 1)[0].rstrip(" ").upper() in RESERVED)


def validate_project(project: str) -> None:
    if not isinstance(project, str):
        raise TypeError("project must be str")
    if (not project or reserved_component(project)
            or any(ord(c) < 32 or c in '<>:"/\\|?*' for c in project)
            or any(0xD800 <= ord(c) <= 0xDFFF for c in project)):
        raise ValueError(f"Invalid Windows project name: {project!r}")
    # Windows counts UTF-16 units; leave room for hash, timestamp, and suffix.
    sample = f"{project}_{'0' * 64}_20000101T000000000Z.data"
    if len(sample.encode("utf-16-le")) // 2 > 255:
        raise ValueError("Project name makes the filename exceed 255 UTF-16 units")


def key_hash(key: str) -> str:
    if not isinstance(key, str):
        raise TypeError("key must be str")
    return hashlib.sha256(key.encode("utf-8", errors="surrogatepass")).hexdigest()


def now() -> datetime:
    return datetime.now(timezone.utc)


def timestamp(value: datetime) -> str:
    return value.strftime("%Y%m%dT%H%M%S") + f"{value.microsecond // 1000:03d}Z"


def encode(data: bytes | str) -> tuple[bytes, str]:
    if isinstance(data, bytes):
        return data, "bytes"
    if isinstance(data, str):
        return data.encode("utf-8", errors="surrogatepass"), "str"
    raise TypeError("data must be bytes or str")


def make_metadata(project: str, key: str, body: bytes, kind: str,
                  saved: datetime) -> dict:
    return {
        "format_version": 1, "project": project, "key": key,
        "saved_at": saved.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "kind": kind, "size_bytes": len(body),
        "sha256": hashlib.sha256(body).hexdigest(),
    }


def validate_metadata(value: object, project: str, key: str, stamp: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError("Metadata is not an object")
    if (type(value.get("format_version")) is not int
            or value["format_version"] != 1
            or value.get("project") != project or value.get("key") != key
            or value.get("kind") not in ("bytes", "str")
            or type(value.get("size_bytes")) is not int or value["size_bytes"] < 0
            or not isinstance(value.get("sha256"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", value["sha256"])):
        raise ValueError("Metadata fields are invalid or do not match the requested cache")
    saved_at = value.get("saved_at")
    if not isinstance(saved_at, str) or not saved_at.endswith("Z"):
        raise ValueError("Invalid saved_at")
    saved = datetime.fromisoformat(saved_at.replace("Z", "+00:00"))
    if timestamp(saved) != stamp:
        raise ValueError("Metadata timestamp does not match filename")
    return value


def decode(body: bytes, value: dict) -> bytes | str:
    if len(body) != value["size_bytes"]:
        raise ValueError("Cache body size mismatch")
    if hashlib.sha256(body).hexdigest() != value["sha256"]:
        raise ValueError("Cache body SHA-256 mismatch")
    if value["kind"] == "str":
        return body.decode("utf-8", errors="surrogatepass")
    return body

