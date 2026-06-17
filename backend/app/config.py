from pydantic_settings import BaseSettings

VERSION = "0.1.0"


class Settings(BaseSettings):
    # LLM
    OPENAI_API_KEY: str = ""
    CONTEXTLENS_EMBEDDING_MODEL: str = "text-embedding-3-small"
    CONTEXTLENS_JUDGE_MODEL: str = "gpt-4o-mini"
    CONTEXTLENS_DECOMPOSE_MODEL: str = "gpt-4o-mini"

    # Auth
    CONTEXTLENS_LOCAL_API_KEY: str = "local_dev_key_change_me"

    # Database
    POSTGRES_USER: str = "contextlens"
    POSTGRES_PASSWORD: str = "contextlens"
    POSTGRES_DB: str = "contextlens"
    DATABASE_URL: str = "postgresql://contextlens:contextlens@postgres:5432/contextlens"

    # Redis
    REDIS_URL: str = "redis://redis:6379/0"

    # Pipeline
    ATTRIBUTION_THRESHOLD: float = 0.75
    DAILY_PROCESSING_LIMIT: int = 10000
    HOURLY_INGEST_RATE_LIMIT: int = 1000
    PER_MINUTE_RATE_LIMIT: int = 100

    # Clustering
    CLUSTERING_MIN_TRACES: int = 10
    CLUSTERING_K: int = 8

    # Dashboard
    NEXT_PUBLIC_API_URL: str = "http://localhost:8000"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
