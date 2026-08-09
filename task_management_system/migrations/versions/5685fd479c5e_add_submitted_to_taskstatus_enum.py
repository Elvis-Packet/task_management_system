"""add SUBMITTED to taskstatus enum

Revision ID: 5685fd479c5e
Revises: 817084b1d72b
Create Date: 2026-08-09 02:51:15.220924

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '5685fd479c5e'
down_revision = '817084b1d72b'
branch_labels = None
depends_on = None


def upgrade():
    # Postgres native enum types don't pick up new Python Enum members
    # automatically — autogenerate only detects column/table changes, not
    # enum-label changes, so this has to be added explicitly.
    op.execute("ALTER TYPE taskstatus ADD VALUE IF NOT EXISTS 'SUBMITTED' BEFORE 'PENDING'")


def downgrade():
    # Postgres does not support dropping a value from an enum type.
    # Downgrading this migration is a no-op; a full downgrade would require
    # recreating the type without 'SUBMITTED'.
    pass
