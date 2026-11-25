"""Media storage. Local disk is the development default; S3 is the durable deployment store.

A stored media key is either a local path (local backend, and every record written before S3
was enabled) or an ``s3://bucket/key`` URI. Reads dispatch on the key, not on the current
setting, so switching backends never breaks existing cases.

With S3, the bucket holds the record copy. Local disk keeps a disposable cache under
``<report_media_dir>/s3-cache`` because detectors, playback and the case assistant read files.
Deleting the cache is safe; files are downloaded again on the next read.
"""

import shutil
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from deeptrace.config import settings

S3_PREFIX = "s3://"


class ObjectStore(Protocol):
    def put_file(self, key: str, source: Path) -> str: ...

    def resolve(self, key: str) -> Path: ...

    def delete(self, key: str) -> None: ...


class LocalObjectStore:
    """Stores files under ``report_media_dir``. Keys it returns are full local paths."""

    def __init__(self, root: Path | None = None):
        self.root = root or settings.report_media_dir

    def put_file(self, key: str, source: Path) -> str:
        target = self.root / key
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        return str(target)

    def resolve(self, key: str) -> Path:
        path = Path(key)
        return path if path.is_absolute() or path.is_file() else self.root / key

    def delete(self, key: str) -> None:
        self.resolve(key).unlink(missing_ok=True)


class S3ObjectStore:
    """S3-backed store. boto3 is imported only when S3 is used. AWS errors surface as OSError."""

    def __init__(self, bucket: str, prefix: str = "deeptrace", cache_dir: Path | None = None):
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self.cache_dir = cache_dir or settings.report_media_dir / "s3-cache"

    def put_file(self, key: str, source: Path) -> str:
        object_key = f"{self.prefix}/media/{key}" if self.prefix else f"media/{key}"
        try:
            _s3_client().upload_file(str(source), self.bucket, object_key)
        except Exception as exc:  # botocore errors are not importable without boto3
            raise OSError(f"S3 upload failed: {type(exc).__name__}") from exc
        uri = f"{S3_PREFIX}{self.bucket}/{object_key}"
        cached = self._cache_path(uri)
        cached.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, cached)
        return uri

    def resolve(self, key: str) -> Path:
        cached = self._cache_path(key)
        if cached.is_file():
            return cached
        bucket, object_key = parse_s3_uri(key)
        cached.parent.mkdir(parents=True, exist_ok=True)
        partial = cached.with_name(f".{cached.name}.{uuid4().hex}.part")
        try:
            _s3_client().download_file(bucket, object_key, str(partial))
            partial.replace(cached)
        except Exception as exc:
            partial.unlink(missing_ok=True)
            raise OSError(f"S3 download failed: {type(exc).__name__}") from exc
        return cached

    def delete(self, key: str) -> None:
        bucket, object_key = parse_s3_uri(key)
        try:
            _s3_client().delete_object(Bucket=bucket, Key=object_key)
        except Exception as exc:
            raise OSError(f"S3 delete failed: {type(exc).__name__}") from exc
        finally:
            self._cache_path(key).unlink(missing_ok=True)

    def _cache_path(self, key: str) -> Path:
        bucket, object_key = parse_s3_uri(key)
        parts = [part for part in object_key.split("/") if part not in ("", ".", "..")]
        return self.cache_dir.joinpath(bucket, *parts)


def parse_s3_uri(key: str) -> tuple[str, str]:
    if not key.startswith(S3_PREFIX) or "/" not in key[len(S3_PREFIX):]:
        raise ValueError("Not an S3 media key")
    bucket, object_key = key[len(S3_PREFIX):].split("/", 1)
    if not bucket or not object_key:
        raise ValueError("Not an S3 media key")
    return bucket, object_key


def _s3_client():
    import boto3
    region = settings.aws_region
    return boto3.client("s3", region_name=region) if region else boto3.client("s3")


def get_store() -> ObjectStore:
    """Store for new uploads, chosen by ``DEEPTRACE_STORAGE_BACKEND``."""
    if settings.storage_backend == "s3":
        if not settings.s3_bucket:
            raise RuntimeError("DEEPTRACE_S3_BUCKET is required when storage backend is s3")
        return S3ObjectStore(settings.s3_bucket, settings.s3_prefix)
    return LocalObjectStore()


def store_for(key: str) -> ObjectStore:
    """Store that owns an existing key, whatever the current backend setting is."""
    if key.startswith(S3_PREFIX):
        bucket, _ = parse_s3_uri(key)
        return S3ObjectStore(bucket, settings.s3_prefix)
    return LocalObjectStore()


def persist_media(report_id: str, source: Path, filename: str) -> str:
    """Save an uploaded recording; returns the key to store in the report and workflow records."""
    return get_store().put_file(f"{report_id}/{Path(filename).name}", source)


def resolve_media(key: str | None) -> Path | None:
    """Local readable path for a stored key, downloading from S3 if needed; None when unavailable."""
    if not key:
        return None
    try:
        path = store_for(key).resolve(key)
    except (OSError, ValueError):
        return None
    return path if path.is_file() else None


def delete_media(key: str | None) -> None:
    if key:
        store_for(key).delete(key)


def s3_uri(key: str | None) -> str | None:
    return key if key and key.startswith(S3_PREFIX) else None
