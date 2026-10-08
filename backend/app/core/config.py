"""Environment-backed application settings."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


class Settings(BaseSettings):
    app_name: str = "FinSight API"
    environment: str = "development"
    finbert_model_id: str = "ProsusAI/finbert"
    database_host: str = "localhost"
    postgres_db: str = "finsight"
    postgres_user: str = "finsight"
    postgres_password: str | None = None
    postgres_port: int = 5432

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def database_url(self) -> URL:
        """Build the database URL from the same variables used by Compose."""
        if not self.postgres_password:
            raise RuntimeError(
                "POSTGRES_PASSWORD is not configured. Set it in the environment or backend/.env."
            )
        return URL.create(
            drivername="postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password,
            host=self.database_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )


@lru_cache
def get_settings() -> Settings:
    """Return cached settings so configuration is read once per process."""
    return Settings()
