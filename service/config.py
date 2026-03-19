from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://sre:sre@localhost:5432/jobs"
    REDIS_URL: str = "redis://localhost:6379"
    JOB_QUEUE_KEY: str = "job_queue"

settings = Settings()