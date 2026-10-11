"""Persist automatic news-ingestion status and archive cursor."""

from alembic import op
import sqlalchemy as sa

revision = "20261009_05"
down_revision = "20261009_04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ingestion_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("latest_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("latest_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archive_day", sa.String(length=10), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_result", sa.JSON(), nullable=True),
        sa.Column("relevance_backfill_before_id", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("ingestion_state")
