from functools import lru_cache

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_JWT_SECRET = "dev-only-secret-change-me-before-any-real-use"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "development"  # development | test | production
    log_level: str = "INFO"
    cors_origins: list[str] = ["http://localhost:3000"]

    # Postgres in production. SQLite is the zero-setup default for local development and tests.
    database_url: str = "sqlite+aiosqlite:///./claimshield.db"
    redis_url: str | None = None

    # Workers. With no Redis the detection pipeline runs in-process after the response is sent.
    sync_processing: bool | None = None

    # ML model server (the training machine). Unset means "score with the local artifacts".
    ml_server_url: str | None = Field(default=None, validation_alias=AliasChoices("ML_SERVER_URL", "MODEL_SERVER_URL", "ml_server_url"))
    ml_server_timeout: float = 10.0
    ml_fallback_enabled: bool = True
    artifacts_dir: str = "artifacts"

    # Investigation copilot (Ollama Cloud)
    ollama_url: str = "https://ollama.com"
    ollama_api_key: str | None = None
    ollama_model: str = "gpt-oss:120b"
    ollama_timeout: float = 60.0

    # Public SIU origin used in outbound webhook links (the existing route is /cases/{id}).
    frontend_url: str = "http://localhost:3000"
    # Used only by the local demo tenant seed; Pydantic also reads these from backend/.env.
    demo_webhook_url: str = "http://localhost:3002/api/webhooks/claimshield"
    demo_webhook_secret: str = Field(default="demo_webhook_secret", repr=False)
    demo_api_key: str = Field(default="demo_api_key_12345", repr=False)

    # Event-driven ingestion
    aws_region: str = "us-east-1"
    sqs_queue_url: str | None = None
    sns_topic_arn: str | None = None

    # Auth. HS256 with jwt_secret for development; set clerk_jwks_url to verify Clerk-issued tokens.
    jwt_secret: str = DEV_JWT_SECRET
    jwt_algorithm: str = "HS256"
    clerk_jwks_url: str | None = None
    clerk_issuer: str | None = None

    sentry_dsn: str | None = None

    enable_graph_analytics: bool = True
    enable_temporal_analytics: bool = True
    enable_copilot: bool = True
    enable_faiss: bool = True
    enable_similarity: bool = True

    case_risk_threshold: float = 0.7
    retrain_threshold: int = 100
    rate_limit_per_minute: int = 600
    batch_max_claims: int = 1000
    audit_retention_days: int = 2555  # 7 years

    @field_validator("redis_url", "ml_server_url", "ollama_api_key", "sqs_queue_url", "sns_topic_arn", "clerk_jwks_url", "clerk_issuer", "sentry_dsn", "sync_processing", mode="before")
    @classmethod
    def _blank_is_unset(cls, value):
        # `REDIS_URL=` in a .env file means "not configured", not "connect to an empty address".
        return None if isinstance(value, str) and not value.strip() else value

    @property
    def is_production(self) -> bool:
        return self.env == "production"

    @property
    def process_inline(self) -> bool:
        if self.sync_processing is not None:
            return self.sync_processing
        return self.redis_url is None

    def validate_for_startup(self) -> None:
        if self.is_production and self.jwt_secret == DEV_JWT_SECRET and not self.clerk_jwks_url:
            raise RuntimeError("Set JWT_SECRET or CLERK_JWKS_URL before running with ENV=production.")
        if self.is_production and self.database_url.startswith("sqlite"):
            raise RuntimeError("SQLite is for development only. Set DATABASE_URL to PostgreSQL for production.")


@lru_cache
def get_settings() -> Settings:
    return Settings()
