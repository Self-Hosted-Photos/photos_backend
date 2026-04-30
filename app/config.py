from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Database
    database_url: str = "postgresql+asyncpg://pixelvault:pixelvault@localhost:5432/pixelvault"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # JWT
    secret_key: str = "dev-secret-key-change-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # Storage
    storage_backend: str = "local"
    storage_root: str = "/storage"

    # CORS — comma-separated string parsed into a list
    allowed_origins: str = "http://localhost:5173,http://localhost:5174"

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    # Email
    smtp_enabled: bool = False
    smtp_host: str = "smtp.example.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    email_from: str = "Pixel Vault <noreply@example.com>"

    # App
    app_env: str = "development"
    base_url: str = "http://localhost:8000"
    admin_email: str = "admin@example.com"

    # Quotas
    default_storage_quota_bytes: int = 10 * 1024 * 1024 * 1024  # 10 GB


@lru_cache
def get_settings() -> Settings:
    return Settings()
