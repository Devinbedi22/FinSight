"""Add persisted news intelligence fields without changing existing records."""

from alembic import op
import sqlalchemy as sa

revision = "20261121_06"
down_revision = "20261009_05"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "news_articles",
        sa.Column("sentiment_status", sa.String(length=24), nullable=False,
                  server_default="not_processed"),
    )
    op.add_column("news_articles", sa.Column("sentiment_model", sa.String(length=255), nullable=True))
    op.add_column("news_articles", sa.Column("sentiment_model_version", sa.String(length=128), nullable=True))
    op.add_column("news_articles", sa.Column("sentiment_inferred_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("news_articles", sa.Column("sentiment_error", sa.Text(), nullable=True))
    op.add_column("news_articles", sa.Column("canonical_url", sa.Text(), nullable=True))
    op.add_column(
        "news_articles",
        sa.Column("financial_events", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.create_index("ix_news_articles_canonical_url", "news_articles", ["canonical_url"])


def downgrade() -> None:
    op.drop_index("ix_news_articles_canonical_url", table_name="news_articles")
    op.drop_column("news_articles", "financial_events")
    op.drop_column("news_articles", "canonical_url")
    op.drop_column("news_articles", "sentiment_error")
    op.drop_column("news_articles", "sentiment_inferred_at")
    op.drop_column("news_articles", "sentiment_model_version")
    op.drop_column("news_articles", "sentiment_model")
    op.drop_column("news_articles", "sentiment_status")
