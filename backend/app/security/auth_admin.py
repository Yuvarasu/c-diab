from typing import Protocol

import httpx


class AuthAdmin(Protocol):
    def delete_user(self, user_id: str) -> None: ...


class NoopAuthAdmin:
    def delete_user(self, user_id: str) -> None:
        return None


class SupabaseAuthAdmin:
    def __init__(self, url: str, service_key: str):
        self.url, self.key = url.rstrip("/"), service_key

    def delete_user(self, user_id: str) -> None:
        r = httpx.delete(f"{self.url}/auth/v1/admin/users/{user_id}", timeout=20,
                         headers={"Authorization": f"Bearer {self.key}", "apikey": self.key})
        if r.status_code >= 300 and r.status_code != 404:
            raise RuntimeError(f"auth user deletion failed ({r.status_code})")
