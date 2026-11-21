"""Object storage. Local disk is the development implementation; S3 is the deployment seam."""

from pathlib import Path
from typing import Protocol

from deeptrace.config import settings


class ObjectStore(Protocol):
    def put_file(self, key: str, source: Path) -> str: ...

    def resolve(self, key: str) -> Path: ...


class LocalObjectStore:
    def __init__(self, root: Path | None = None):
        self.root = root or settings.report_media_dir

    def put_file(self, key: str, source: Path) -> str:
        target = self.root / key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
        return key

    def resolve(self, key: str) -> Path:
        path = Path(key)
        if path.is_file():
            return path
        return self.root / key


class S3ObjectStore:
    """AWS-compatible store. boto3 is imported only when this backend is selected."""

    def __init__(self, bucket: str, prefix: str = "deeptrace"):
        self.bucket = bucket
        self.prefix = prefix.strip("/")

    def put_file(self, key: str, source: Path) -> str:
        import boto3
        object_key = f"{self.prefix}/{key}"
        boto3.client("s3").upload_file(str(source), self.bucket, object_key)
        return object_key

    def resolve(self, key: str) -> Path:
        raise RuntimeError("S3 objects are streamed by the deployment layer, not read as local paths")


def get_store() -> ObjectStore:
    if settings.storage_backend == "s3":
        if not settings.s3_bucket:
            raise RuntimeError("DEEPTRACE_S3_BUCKET is required when storage backend is s3")
        return S3ObjectStore(settings.s3_bucket, settings.s3_prefix)
    return LocalObjectStore()
