from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional


def _iter_files(root: Path) -> Iterable[Path]:
    for p in root.rglob("*"):
        if p.is_file():
            yield p


def _safe_mkdir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class StorageCapsule:
    backend: str
    historical_root: str
    object_prefix: str
    fetched_ok: bool

    def as_dict(self) -> Dict[str, object]:
        return {
            "backend": self.backend,
            "historical_root": self.historical_root,
            "object_prefix": self.object_prefix,
            "fetched_ok": bool(self.fetched_ok),
        }


class StorageBackend:
    def promote_step_dir(self, stream_id: str, step_number: int, src_step_dir: Path) -> StorageCapsule:
        raise NotImplementedError

    def fetch_step_dir(self, stream_id: str, step_number: int, dst_step_dir: Path) -> StorageCapsule:
        raise NotImplementedError


class FilesystemStorageBackend(StorageBackend):
    def __init__(self, historical_root: Path):
        self.historical_root = historical_root

    def _dst_dir(self, stream_id: str, step_number: int) -> Path:
        return self.historical_root / str(stream_id) / f"step_{int(step_number):06d}"

    def promote_step_dir(self, stream_id: str, step_number: int, src_step_dir: Path) -> StorageCapsule:
        dst_dir = self._dst_dir(stream_id, step_number)
        object_prefix = f"{stream_id}/step_{int(step_number):06d}/"
        _safe_mkdir(dst_dir.parent)

        if dst_dir.exists():
            return StorageCapsule(
                backend="filesystem",
                historical_root=str(self.historical_root),
                object_prefix=object_prefix,
                fetched_ok=False,
            )

        shutil.copytree(src_step_dir, dst_dir)
        return StorageCapsule(
            backend="filesystem",
            historical_root=str(self.historical_root),
            object_prefix=object_prefix,
            fetched_ok=True,
        )

    def fetch_step_dir(self, stream_id: str, step_number: int, dst_step_dir: Path) -> StorageCapsule:
        src_dir = self._dst_dir(stream_id, step_number)
        object_prefix = f"{stream_id}/step_{int(step_number):06d}/"
        _safe_mkdir(dst_step_dir.parent)

        if not src_dir.exists():
            return StorageCapsule(
                backend="filesystem",
                historical_root=str(self.historical_root),
                object_prefix=object_prefix,
                fetched_ok=False,
            )

        if dst_step_dir.exists():
            return StorageCapsule(
                backend="filesystem",
                historical_root=str(self.historical_root),
                object_prefix=object_prefix,
                fetched_ok=True,
            )

        shutil.copytree(src_dir, dst_step_dir)
        return StorageCapsule(
            backend="filesystem",
            historical_root=str(self.historical_root),
            object_prefix=object_prefix,
            fetched_ok=True,
        )


class S3StorageBackend(StorageBackend):
    def __init__(
        self,
        bucket: str,
        prefix: str = "",
        region: str = "",
        endpoint_url: str = "",
        access_key_id: str = "",
        secret_access_key: str = "",
        client: object | None = None,
    ):
        self.bucket = bucket.strip()
        self.prefix = prefix.strip()
        if self.prefix and not self.prefix.endswith("/"):
            self.prefix += "/"
        self.region = region.strip()
        self.endpoint_url = endpoint_url.strip()
        self.access_key_id = access_key_id.strip()
        self.secret_access_key = secret_access_key.strip()
        self._client = client

    def _capsule(self, stream_id: str, step_number: int, fetched_ok: bool) -> StorageCapsule:
        object_prefix = f"{stream_id}/step_{int(step_number):06d}/"
        root = f"s3://{self.bucket}/{self.prefix}".rstrip("/")
        return StorageCapsule(
            backend="s3",
            historical_root=root,
            object_prefix=object_prefix,
            fetched_ok=bool(fetched_ok),
        )

    def _s3(self):
        if self._client is not None:
            return self._client

        try:
            import boto3  # type: ignore
        except Exception as e:
            raise RuntimeError(f"S3_NOT_AVAILABLE {e.__class__.__name__}") from e

        kw = {}
        if self.region:
            kw["region_name"] = self.region
        if self.endpoint_url:
            kw["endpoint_url"] = self.endpoint_url
        if self.access_key_id and self.secret_access_key:
            kw["aws_access_key_id"] = self.access_key_id
            kw["aws_secret_access_key"] = self.secret_access_key
        return boto3.client("s3", **kw)

    def promote_step_dir(self, stream_id: str, step_number: int, src_step_dir: Path) -> StorageCapsule:
        if not self.bucket:
            return self._capsule(stream_id, step_number, False)

        s3 = self._s3()
        key_prefix = f"{self.prefix}{stream_id}/step_{int(step_number):06d}/"

        try:
            for fp in _iter_files(src_step_dir):
                rel = fp.relative_to(src_step_dir).as_posix()
                key = key_prefix + rel
                s3.upload_file(str(fp), self.bucket, key)
            return self._capsule(stream_id, step_number, True)
        except Exception:
            return self._capsule(stream_id, step_number, False)

    def fetch_step_dir(self, stream_id: str, step_number: int, dst_step_dir: Path) -> StorageCapsule:
        if not self.bucket:
            return self._capsule(stream_id, step_number, False)

        s3 = self._s3()
        key_prefix = f"{self.prefix}{stream_id}/step_{int(step_number):06d}/"

        try:
            _safe_mkdir(dst_step_dir)
            paginator = s3.get_paginator("list_objects_v2")
            found_any = False

            for page in paginator.paginate(Bucket=self.bucket, Prefix=key_prefix):
                for obj in page.get("Contents", []) or []:
                    k = str(obj.get("Key") or "")
                    if not k or not k.startswith(key_prefix):
                        continue
                    found_any = True
                    rel = k[len(key_prefix) :]
                    if not rel or rel.endswith("/"):
                        continue
                    out_path = dst_step_dir / rel
                    _safe_mkdir(out_path.parent)
                    s3.download_file(self.bucket, k, str(out_path))

            return self._capsule(stream_id, step_number, found_any)
        except Exception:
            return self._capsule(stream_id, step_number, False)


def build_storage_from_env(historical_root: Path) -> StorageBackend:
    backend = (os.getenv("VSC_STORAGE_BACKEND", "filesystem") or "filesystem").strip().lower()
    if backend == "s3":
        return S3StorageBackend(
            bucket=os.getenv("VSC_S3_BUCKET", "") or "",
            prefix=os.getenv("VSC_S3_PREFIX", "") or "",
            region=os.getenv("VSC_S3_REGION", "") or "",
            endpoint_url=os.getenv("VSC_S3_ENDPOINT_URL", "") or "",
            access_key_id=os.getenv("VSC_S3_ACCESS_KEY_ID", "") or "",
            secret_access_key=os.getenv("VSC_S3_SECRET_ACCESS_KEY", "") or "",
        )
    return FilesystemStorageBackend(historical_root=historical_root)
