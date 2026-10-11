"""Persist per-ticker FinBERT impact-tone outputs."""

from alembic import op
import sqlalchemy as sa

revision = "20261009_02"
down_revision = "20261009_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "news_articles",
        sa.Column("impact_predictions", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )


def downgrade() -> None:
    op.drop_column("news_articles", "impact_predictions")
