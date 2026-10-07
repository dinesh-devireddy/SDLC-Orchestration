"""Initial links table."""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "links",
        sa.Column("code", sa.String(32), primary_key=True),
        sa.Column("destination", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(27), nullable=False),
        sa.Column("expires_at", sa.String(27), nullable=True),
        sa.Column("clicks", sa.Integer(), nullable=False),
        sa.CheckConstraint("clicks >= 0", name="ck_links_clicks"),
    )


def downgrade():
    op.drop_table("links")
