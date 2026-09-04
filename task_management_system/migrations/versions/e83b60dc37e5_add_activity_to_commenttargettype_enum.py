"""add ACTIVITY to commenttargettype enum

Revision ID: e83b60dc37e5
Revises: 26db45058ef7
Create Date: 2026-08-09 13:48:47.155957

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e83b60dc37e5'
down_revision = '26db45058ef7'
branch_labels = None
depends_on = None


def upgrade():
    # Postgres native enum types don't pick up new Python Enum members
    # automatically — autogenerate only detects column/table changes, not
    # enum-label changes, so this has to be added explicitly.
    op.execute("ALTER TYPE commenttargettype ADD VALUE IF NOT EXISTS 'ACTIVITY'")


def downgrade():
    # Postgres does not support dropping a value from an enum type.
    pass
