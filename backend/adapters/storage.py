"""Object storage behind a narrow interface: OCI Object Storage over its S3-compatible API.

Two buckets: public objects are served from `STORAGE_PUBLIC_BASE_URL`, private ones only through
short-lived presigned GET URLs. The fake in `adapters/fake_storage.py` stands in for tests.
"""

from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum
from functools import cache
from typing import TYPE_CHECKING, Protocol

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from django.conf import settings

if TYPE_CHECKING:
    from mypy_boto3_s3.client import S3Client


class Bucket(StrEnum):
    PUBLIC = "public"
    PRIVATE = "private"


class StorageNotConfigured(Exception):
    """The STORAGE_* settings are missing; media features are off until they are set."""


@dataclass(frozen=True)
class StoredObject:
    size: int
    content_type: str


@dataclass(frozen=True)
class PresignedUpload:
    url: str
    headers: dict[str, str]  # the client must send these with the PUT


class ObjectStorage(Protocol):
    def presign_put(
        self, bucket: Bucket, key: str, content_type: str, expires_in: timedelta
    ) -> PresignedUpload: ...

    def presign_get(self, bucket: Bucket, key: str, expires_in: timedelta) -> str: ...

    def put(self, bucket: Bucket, key: str, data: bytes, content_type: str) -> None: ...

    def head(self, bucket: Bucket, key: str) -> StoredObject | None:
        """The object's size and type, or None when it does not exist."""
        ...

    def delete(self, bucket: Bucket, key: str) -> None: ...

    def public_url(self, key: str) -> str:
        """Where a public-bucket object is served from. No network call."""
        ...


class S3ObjectStorage:
    def __init__(
        self,
        *,
        endpoint_url: str,
        region: str,
        access_key: str,
        secret_key: str,
        public_bucket: str,
        private_bucket: str,
        public_base_url: str,
    ) -> None:
        self._buckets = {Bucket.PUBLIC: public_bucket, Bucket.PRIVATE: private_bucket}
        self._public_base_url = public_base_url.rstrip("/") + "/"
        self._client: S3Client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            region_name=region,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            # OCI's S3 compatibility needs path-style addresses and SigV4 for presigned URLs,
            # and rejects boto3's default aws-chunked request checksums.
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
                request_checksum_calculation="when_required",
                response_checksum_validation="when_required",
            ),
        )

    def presign_put(
        self, bucket: Bucket, key: str, content_type: str, expires_in: timedelta
    ) -> PresignedUpload:
        url = self._client.generate_presigned_url(
            "put_object",
            Params={"Bucket": self._buckets[bucket], "Key": key, "ContentType": content_type},
            ExpiresIn=int(expires_in.total_seconds()),
        )
        return PresignedUpload(url=url, headers={"Content-Type": content_type})

    def presign_get(self, bucket: Bucket, key: str, expires_in: timedelta) -> str:
        url: str = self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._buckets[bucket], "Key": key},
            ExpiresIn=int(expires_in.total_seconds()),
        )
        return url

    def put(self, bucket: Bucket, key: str, data: bytes, content_type: str) -> None:
        self._client.put_object(
            Bucket=self._buckets[bucket], Key=key, Body=data, ContentType=content_type
        )

    def head(self, bucket: Bucket, key: str) -> StoredObject | None:
        try:
            found = self._client.head_object(Bucket=self._buckets[bucket], Key=key)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in {"404", "NoSuchKey", "NotFound"}:
                return None
            raise
        return StoredObject(size=found["ContentLength"], content_type=found.get("ContentType", ""))

    def delete(self, bucket: Bucket, key: str) -> None:
        self._client.delete_object(Bucket=self._buckets[bucket], Key=key)

    def public_url(self, key: str) -> str:
        return self._public_base_url + key


_SETTINGS = (
    "STORAGE_ENDPOINT_URL",
    "STORAGE_REGION",
    "STORAGE_ACCESS_KEY",
    "STORAGE_SECRET_KEY",
    "STORAGE_PUBLIC_BUCKET",
    "STORAGE_PRIVATE_BUCKET",
    "STORAGE_PUBLIC_BASE_URL",
)


def get_storage() -> ObjectStorage:
    """The storage the services use. Tests replace this seam (see tests/conftest.py)."""
    values = tuple(getattr(settings, name, "") for name in _SETTINGS)
    missing = [name for name, value in zip(_SETTINGS, values, strict=True) if not value]
    if missing:
        raise StorageNotConfigured(f"오브젝트 스토리지 설정이 없습니다: {', '.join(missing)}")
    return _build(*values)


@cache
def _build(
    endpoint_url: str,
    region: str,
    access_key: str,
    secret_key: str,
    public_bucket: str,
    private_bucket: str,
    public_base_url: str,
) -> ObjectStorage:
    return S3ObjectStorage(
        endpoint_url=endpoint_url,
        region=region,
        access_key=access_key,
        secret_key=secret_key,
        public_bucket=public_bucket,
        private_bucket=private_bucket,
        public_base_url=public_base_url,
    )
