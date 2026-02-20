from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")

    # App
    APP_NAME: str = "RAG Eval Harness"
    APP_VERSION: str = "1.0.0"
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@db:5432/rageval"
    SYNC_DATABASE_URL: str = "postgresql://postgres:postgres@db:5432/rageval"

    # Redis / Celery
    REDIS_URL: str = "redis://redis:6379/0"
    CELERY_BROKER_URL: str = "redis://redis:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/2"

    # LLM for evaluation
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o"
    EVAL_LLM_PROVIDER: str = "openai"  # openai | azure | anthropic

    # Release Gate defaults
    DEFAULT_FAITHFULNESS_THRESHOLD: float = 0.7
    DEFAULT_ANSWER_RELEVANCY_THRESHOLD: float = 0.7
    DEFAULT_CONTEXT_PRECISION_THRESHOLD: float = 0.6
    DEFAULT_CONTEXT_RECALL_THRESHOLD: float = 0.6
    DEFAULT_PASS_RATE_THRESHOLD: float = 0.8

    # GitHub
    GITHUB_TOKEN: str = ""


settings = Settings()
