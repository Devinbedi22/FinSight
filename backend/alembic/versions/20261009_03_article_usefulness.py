"""Persist article market-usefulness classification."""

from alembic import op
import sqlalchemy as sa

revision = "20261009_03"
down_revision = "20261009_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("news_articles", sa.Column("usefulness", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("news_articles", "usefulness")
