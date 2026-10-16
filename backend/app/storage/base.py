from pathlib import Path
from typing import Protocol

import httpx


class StorageError(Exception):
    pass


class StorageBackend(Protocol):
    def put(self, path: str, data: bytes, content_type: str) -> None: ...
    def get(self, path: str) -> bytes: ...
    def delete(self, path: str) -> None: ...


class LocalStorage:
    """Development storage on local disk. Paths are always server generated."""

    def __init__(self, base_dir: str):
        self.base = Path(base_dir).resolve()
        self.base.mkdir(parents=True, exist_ok=True)

    def _p(self, path: str) -> Path:
        p = (self.base / path).resolve()
        if self.base not in p.parents:
            raise StorageError("invalid storage path")
        return p

    def put(self, path: str, data: bytes, content_type: str) -> None:
        p = self._p(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def get(self, path: str) -> bytes:
        try:
            return self._p(path).read_bytes()
        except FileNotFoundError as exc:
            raise StorageError("object not found") from exc

    def delete(self, path: str) -> None:
        self._p(path).unlink(missing_ok=True)


class SupabaseStorage:
    """Private Supabase Storage bucket accessed with the service-role key (server side only)."""

    def __init__(self, url: str, service_key: str, bucket: str):
        self.base = f"{url.rstrip('/')}/storage/v1/object/{bucket}"
        self.headers = {"Authorization": f"Bearer {service_key}", "apikey": service_key}

    def put(self, path: str, data: bytes, content_type: str) -> None:
        r = httpx.post(f"{self.base}/{path}", content=data, timeout=30,
                       headers={**self.headers, "Content-Type": content_type, "x-upsert": "true"})
        if r.status_code >= 300:
            raise StorageError(f"upload failed ({r.status_code})")

    def get(self, path: str) -> bytes:
        r = httpx.get(f"{self.base}/{path}", headers=self.headers, timeout=30)
        if r.status_code >= 300:
            raise StorageError(f"download failed ({r.status_code})")
        return r.content

    def delete(self, path: str) -> None:
        r = httpx.delete(f"{self.base}/{path}", headers=self.headers, timeout=30)
        if r.status_code >= 300 and r.status_code != 404:
            raise StorageError(f"delete failed ({r.status_code})")
