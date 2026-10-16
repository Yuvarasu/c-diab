from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["development", "test", "preview", "production"] = "development"
    database_url: str = "sqlite:///./cdiab_dev.db"
    cors_origins: list[str] = []

    # Supabase (server side only)
    supabase_url: str = ""
    supabase_jwt_secret: str = ""  # legacy HS256 projects; leave empty when using JWKS signing keys
    supabase_service_role_key: str = ""
    supabase_storage_bucket: str = "screening-images"
    jwt_audience: str = "authenticated"

    storage_backend: Literal["local", "supabase"] = "local"
    local_storage_dir: str = "./.local_storage"
    max_image_bytes: int = 8 * 1024 * 1024

    # AI
    ai_backend: Literal["demo", "http"] = "demo"
    model_service_url: str = ""
    model_service_token: str = ""
    demo_force_outcome: Literal["", "none", "superficial", "deep", "undetermined"] = ""
    quality_min_blur: float = 25.0  # Laplacian variance; calibrate with real photos

    # Policy
    policy_config_path: str = "policy/policy.default.json"
    allow_demo_eligibility: bool = False  # lets DEMO results unlock checkout (never in production)

    # Payments
    payment_provider: Literal["mock", "razorpay"] = "mock"
    mock_payment_secret: str = "dev-only-mock-secret"
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""

    shipping_flat_paise: int = 9900
    free_shipping_threshold_paise: int = 199900
    rate_limit_enabled: bool = True

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @model_validator(mode="after")
    def _guards(self):
        problems: list[str] = []
        if self.ai_backend == "http" and not self.model_service_url:
            problems.append("AI_BACKEND=http requires MODEL_SERVICE_URL")
        if self.storage_backend == "supabase" and not (self.supabase_url and self.supabase_service_role_key):
            problems.append("STORAGE_BACKEND=supabase requires SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY")
        if self.payment_provider == "razorpay" and not (self.razorpay_key_id and self.razorpay_key_secret):
            problems.append("PAYMENT_PROVIDER=razorpay requires RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET")
        if self.is_production:
            if self.ai_backend == "demo":
                problems.append("production must not use the demo AI (set AI_BACKEND=http with a validated model)")
            if self.demo_force_outcome:
                problems.append("DEMO_FORCE_OUTCOME is not allowed in production")
            if self.allow_demo_eligibility:
                problems.append("ALLOW_DEMO_ELIGIBILITY is not allowed in production")
            if self.payment_provider == "mock":
                problems.append("production must not use the mock payment provider")
            if self.storage_backend == "local":
                problems.append("production must use private Supabase storage")
            if self.database_url.startswith("sqlite"):
                problems.append("production requires a PostgreSQL DATABASE_URL")
            if not self.supabase_url:
                problems.append("production requires SUPABASE_URL for JWT verification")
            if self.payment_provider == "razorpay" and not self.razorpay_webhook_secret:
                problems.append("production Razorpay requires RAZORPAY_WEBHOOK_SECRET")
        if problems:
            raise ValueError("Unsafe or incomplete configuration: " + "; ".join(problems))
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
