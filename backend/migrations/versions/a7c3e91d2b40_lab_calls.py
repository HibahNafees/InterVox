"""usage_limits.lab_calls for the Chat Lab daily cap (T-146)

Revision ID: a7c3e91d2b40
Revises: 0234b00773b2
Create Date: 2026-11-18 20:10:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a7c3e91d2b40'
down_revision = '0234b00773b2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('usage_limits', schema=None) as batch_op:
        batch_op.add_column(sa.Column('lab_calls', sa.Integer(), server_default='0', nullable=False))


def downgrade():
    with op.batch_alter_table('usage_limits', schema=None) as batch_op:
        batch_op.drop_column('lab_calls')
