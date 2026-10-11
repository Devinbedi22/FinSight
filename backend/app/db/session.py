"""Lazy SQLAlchemy engine and request-scoped session dependency."""

from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session

from app.core.config import get_settings


@lru_cache
def get_engine() -> Engine:
    """Create the database engine on first use, not during app startup."""
    url = get_settings().database_url
    if url.drivername.startswith("sqlite"):
        engine = create_engine(url, pool_pre_ping=True, connect_args={"timeout": 30})

        @event.listens_for(engine, "connect")
        def _configure_sqlite(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

        return engine
    return create_engine(url, pool_pre_ping=True)


def get_db() -> Generator[Session, None, None]:
    """Yield a request-scoped SQLAlchemy session."""
    with Session(get_engine()) as session:
        yield session
