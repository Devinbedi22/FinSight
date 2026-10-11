"""Create persisted news article and inference table."""

from alembic import op
import sqlalchemy as sa

revision = "20261009_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "news_articles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=255), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sentiment", sa.String(length=16), nullable=False),
        sa.Column("sentiment_score", sa.Float(), nullable=False),
        sa.Column("sentiment_scores", sa.JSON(), nullable=False),
        sa.Column("ticker_candidates", sa.JSON(), nullable=False),
        sa.UniqueConstraint("url", name="uq_news_articles_url"),
    )
    op.create_index("ix_news_articles_published_at", "news_articles", ["published_at"])


def downgrade() -> None:
    op.drop_index("ix_news_articles_published_at", table_name="news_articles")
    op.drop_table("news_articles")
