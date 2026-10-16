from app.core.config import Settings
from app.storage.base import LocalStorage, StorageBackend, SupabaseStorage


def build_storage(s: Settings) -> StorageBackend:
    if s.storage_backend == "supabase":
        return SupabaseStorage(s.supabase_url, s.supabase_service_role_key, s.supabase_storage_bucket)
    return LocalStorage(s.local_storage_dir)
