import shutil
from pathlib import Path

import pytest

from deeptrace import storage
from deeptrace.config import Settings, settings


class FakeS3:
    """In-memory S3 with the three boto3 calls the store uses."""

    def __init__(self, root: Path):
        self.root = root
        self.fail = False

    def _path(self, bucket: str, key: str) -> Path:
        return self.root / bucket / key

    def upload_file(self, source: str, bucket: str, key: str) -> None:
        if self.fail:
            raise RuntimeError("AccessDenied")
        target = self._path(bucket, key)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    def download_file(self, bucket: str, key: str, target: str) -> None:
        source = self._path(bucket, key)
        if self.fail or not source.is_file():
            raise RuntimeError("NoSuchKey")
        shutil.copy2(source, target)

    def delete_object(self, Bucket: str, Key: str) -> None:
        self._path(Bucket, Key).unlink(missing_ok=True)


@pytest.fixture
def s3(monkeypatch, tmp_path):
    fake = FakeS3(tmp_path / "bucket-store")
    monkeypatch.setattr(storage, "_s3_client", lambda: fake)
    monkeypatch.setattr(settings, "report_media_dir", tmp_path / "media")
    monkeypatch.setattr(settings, "storage_backend", "s3")
    monkeypatch.setattr(settings, "s3_bucket", "case-media")
    monkeypatch.setattr(settings, "s3_prefix", "deeptrace")
    return fake


def upload(tmp_path: Path) -> Path:
    source = tmp_path / "upload.tmp"
    source.write_bytes(b"recording")
    return source


def test_s3_backend_stores_the_record_copy_in_the_bucket_and_caches_locally(s3, tmp_path):
    key = storage.persist_media("report-1", upload(tmp_path), "../clip.mp4")
    assert key == "s3://case-media/deeptrace/media/report-1/clip.mp4"
    assert (s3.root / "case-media/deeptrace/media/report-1/clip.mp4").read_bytes() == b"recording"
    cached = storage.resolve_media(key)
    assert cached == settings.report_media_dir / "s3-cache/case-media/deeptrace/media/report-1/clip.mp4"
    assert storage.s3_uri(key) == key


def test_missing_cache_is_downloaded_again(s3, tmp_path):
    key = storage.persist_media("report-1", upload(tmp_path), "clip.mp4")
    shutil.rmtree(settings.report_media_dir / "s3-cache")
    path = storage.resolve_media(key)
    assert path is not None and path.read_bytes() == b"recording"
    assert not list(path.parent.glob(".*.part"))


def test_delete_removes_object_and_cache(s3, tmp_path):
    key = storage.persist_media("report-1", upload(tmp_path), "clip.mp4")
    cached = storage.resolve_media(key)
    storage.delete_media(key)
    assert not (s3.root / "case-media/deeptrace/media/report-1/clip.mp4").exists()
    assert not cached.exists()
    assert storage.resolve_media(key) is None


def test_aws_failures_surface_as_oserror_or_unavailable_media(s3, tmp_path):
    s3.fail = True
    with pytest.raises(OSError):
        storage.persist_media("report-1", upload(tmp_path), "clip.mp4")
    assert storage.resolve_media("s3://case-media/deeptrace/media/report-1/missing.mp4") is None


def test_local_records_stay_readable_after_switching_to_s3(s3, tmp_path):
    old = tmp_path / "media/report-0/old.mp4"
    old.parent.mkdir(parents=True)
    old.write_bytes(b"legacy")
    assert storage.resolve_media(str(old)) == old
    storage.delete_media(str(old))
    assert not old.exists()


def test_local_backend_keeps_the_existing_layout(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "report_media_dir", tmp_path / "media")
    monkeypatch.setattr(settings, "storage_backend", "local")
    key = storage.persist_media("report-1", upload(tmp_path), "clip.wav")
    assert key == str(tmp_path / "media/report-1/clip.wav")
    assert storage.resolve_media(key).read_bytes() == b"recording"


def test_s3_uri_parsing_rejects_other_values():
    assert storage.parse_s3_uri("s3://bucket/a/b.mp4") == ("bucket", "a/b.mp4")
    for value in ("/data/clip.mp4", "s3://bucket", "s3:///key"):
        with pytest.raises(ValueError):
            storage.parse_s3_uri(value)


def test_s3_backend_requires_a_bucket():
    with pytest.raises(ValueError, match="S3_BUCKET"):
        Settings(_env_file=None, storage_backend="s3")
