"""Environment-backed application settings."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url


class Settings(BaseSettings):
    app_name: str = "FinSight API"
    environment: str = "development"
    finbert_model_id: str = "ProsusAI/finbert"
    financial_relevance_model_id: str = "stocky-ai/fin-impact-xlmr"
    financial_relevance_threshold: float = 0.55
    financial_relevance_max_score: float = 1.0
    financial_relevance_enabled: bool = True
    financialbert_weights_path: str = "app/ml/artifacts/financialbert/model_regressor_weight_v2.pth"
    impact_context_limit: int = 5
    financialbert_news_top_k: int = 5
    cohere_api_key: str | None = None
    cohere_rerank_model: str = "rerank-english-v3.0"
    impact_neutral_band: float = 0.002
    stocky_model_id: str = "stocky-ai/stock-predictor-scratch"
    sp500_constituents_url: str = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"
    us_listed_symbols_url: str = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqtraded.txt"
    google_news_rss_url: str = "https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en"
    news_poll_minutes: int = 15
    news_ingest_limit: int = 50
    news_archive_bootstrap_days: int = 90
    news_archive_bootstrap_articles: int = 5000
    news_ingest_enabled: bool = True
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    database_host: str = "localhost"
    database_dsn: str | None = Field(default=None, validation_alias="DATABASE_URL")
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
        """Resolve SQLite paths from the backend directory, not the launch directory."""
        if self.database_dsn:
            url = make_url(self.database_dsn)
            if url.drivername.startswith("sqlite") and url.database not in (None, ":memory:"):
                database_path = Path(url.database)
                if not database_path.is_absolute():
                    database_path = Path(__file__).resolve().parents[2] / database_path
                return URL.create(url.drivername, database=str(database_path.resolve()))
            return url
        if not self.postgres_password:
            local_db = Path(__file__).resolve().parents[2] / "finsight.db"
            return URL.create("sqlite", database=str(local_db))
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
