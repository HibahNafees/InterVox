"""users.google_sub and nullable password_hash for Google sign-in (T-156)

Revision ID: 5b17f9ca000f
Revises: c4d81f6a9e27
Create Date: 2026-11-22 23:08:37.777962

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = '5b17f9ca000f'
down_revision = 'c4d81f6a9e27'
branch_labels = None
depends_on = None

# A well-formed hash that no password matches, for Google-only accounts on downgrade.
NO_PASSWORD = "pbkdf2:sha256:1$none$0"


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('google_sub', sa.String(length=255), nullable=True))
        batch_op.alter_column('password_hash',
               existing_type=mysql.VARCHAR(length=255),
               nullable=True)
        batch_op.create_unique_constraint('uq_users_google_sub', ['google_sub'])


def downgrade():
    op.execute(
        sa.text("UPDATE users SET password_hash = :h WHERE password_hash IS NULL").bindparams(
            h=NO_PASSWORD
        )
    )
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_constraint('uq_users_google_sub', type_='unique')
        batch_op.alter_column('password_hash',
               existing_type=mysql.VARCHAR(length=255),
               nullable=False)
        batch_op.drop_column('google_sub')
