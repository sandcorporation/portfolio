"""In-memory ObjectStorage for tests: it keeps objects and a log of every call."""

from dataclasses import dataclass, field
from datetime import timedelta

from adapters.storage import Bucket, PresignedUpload, StoredObject


@dataclass
class FakeObjectStorage:
    public_base_url: str = "https://public.test/"
    objects: dict[tuple[Bucket, str], tuple[bytes, str]] = field(default_factory=dict)
    # (operation, bucket, key) in call order.
    calls: list[tuple[str, Bucket, str]] = field(default_factory=list)

    def presign_put(
        self, bucket: Bucket, key: str, content_type: str, expires_in: timedelta
    ) -> PresignedUpload:
        self.calls.append(("presign_put", bucket, key))
        return PresignedUpload(
            url=f"https://upload.test/{bucket}/{key}?expires={int(expires_in.total_seconds())}",
            headers={"Content-Type": content_type},
        )

    def presign_get(
        self, bucket: Bucket, key: str, expires_in: timedelta, *, download_name: str | None = None
    ) -> str:
        self.calls.append(("presign_get", bucket, key))
        url = f"https://download.test/{bucket}/{key}?expires={int(expires_in.total_seconds())}"
        return f"{url}&download={download_name}" if download_name is not None else url

    def put(self, bucket: Bucket, key: str, data: bytes, content_type: str) -> None:
        self.calls.append(("put", bucket, key))
        self.objects[(bucket, key)] = (data, content_type)

    def head(self, bucket: Bucket, key: str) -> StoredObject | None:
        self.calls.append(("head", bucket, key))
        found = self.objects.get((bucket, key))
        return None if found is None else StoredObject(len(found[0]), found[1])

    def delete(self, bucket: Bucket, key: str) -> None:
        self.calls.append(("delete", bucket, key))
        self.objects.pop((bucket, key), None)

    def public_url(self, key: str) -> str:
        return self.public_base_url.rstrip("/") + "/" + key

    def simulate_client_put(self, bucket: Bucket, key: str, data: bytes, content_type: str) -> None:
        """What the browser's PUT to a presigned URL does; it is not a call the server makes."""
        self.objects[(bucket, key)] = (data, content_type)
