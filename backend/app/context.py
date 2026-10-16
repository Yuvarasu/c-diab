from dataclasses import dataclass
from typing import Optional

import jwt
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from app.ai.base import InferenceBackend
from app.ai.factory import build_inference
from app.core.config import Settings
from app.core.db import make_engine, make_session_factory
from app.payments.base import PaymentProvider
from app.payments.factory import build_payments
from app.screening_policy.config import PolicyConfig, load_policy
from app.security.auth_admin import AuthAdmin, NoopAuthAdmin, SupabaseAuthAdmin
from app.security.ratelimit import RateLimiter
from app.storage.base import StorageBackend
from app.storage.factory import build_storage


@dataclass
class AppContext:
    settings: Settings
    engine: Engine
    session_factory: sessionmaker
    storage: StorageBackend
    inference: InferenceBackend
    policy: PolicyConfig
    payments: PaymentProvider
    auth_admin: AuthAdmin
    limiter: RateLimiter
    jwks_client: Optional[jwt.PyJWKClient]


def build_context(s: Settings) -> AppContext:
    engine = make_engine(s.database_url)
    jwks = jwt.PyJWKClient(f"{s.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json", cache_keys=True) if s.supabase_url else None
    admin = SupabaseAuthAdmin(s.supabase_url, s.supabase_service_role_key) if s.supabase_url and s.supabase_service_role_key else NoopAuthAdmin()
    return AppContext(s, engine, make_session_factory(engine), build_storage(s), build_inference(s),
                      load_policy(s.policy_config_path, s.app_env), build_payments(s), admin,
                      RateLimiter(s.rate_limit_enabled), jwks)
