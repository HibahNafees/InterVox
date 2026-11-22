"""usage_limits.voice_replies for the daily Fire voice cap (T-154)

Revision ID: c4d81f6a9e27
Revises: a7c3e91d2b40
Create Date: 2026-11-22 23:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "c4d81f6a9e27"
down_revision = "a7c3e91d2b40"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("usage_limits", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("voice_replies", sa.Integer(), server_default="0", nullable=False)
        )


def downgrade():
    with op.batch_alter_table("usage_limits", schema=None) as batch_op:
        batch_op.drop_column("voice_replies")
