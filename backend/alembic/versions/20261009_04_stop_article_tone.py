"""Stop computing article-level tone; leave legacy values nullable."""

from alembic import op
import sqlalchemy as sa

revision = "20261009_04"
down_revision = "20261009_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("news_articles") as batch:
        batch.alter_column("sentiment", existing_type=sa.String(length=16), nullable=True)
        batch.alter_column("sentiment_score", existing_type=sa.Float(), nullable=True)
        batch.alter_column("sentiment_scores", existing_type=sa.JSON(), nullable=True)


def downgrade() -> None:
    op.execute("UPDATE news_articles SET sentiment = 'neutral' WHERE sentiment IS NULL")
    op.execute("UPDATE news_articles SET sentiment_score = 0 WHERE sentiment_score IS NULL")
    op.execute("UPDATE news_articles SET sentiment_scores = '{}' WHERE sentiment_scores IS NULL")
    with op.batch_alter_table("news_articles") as batch:
        batch.alter_column("sentiment", existing_type=sa.String(length=16), nullable=False)
        batch.alter_column("sentiment_score", existing_type=sa.Float(), nullable=False)
        batch.alter_column("sentiment_scores", existing_type=sa.JSON(), nullable=False)
