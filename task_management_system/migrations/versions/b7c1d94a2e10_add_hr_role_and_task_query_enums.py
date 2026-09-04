"""add HR to userrole and TASK_QUERY to notificationtype

Revision ID: b7c1d94a2e10
Revises: 169fa362c6a9
Create Date: 2026-08-14 10:05:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b7c1d94a2e10'
down_revision = '169fa362c6a9'
branch_labels = None
depends_on = None


def upgrade():
    # Postgres native enum types don't pick up new Python Enum members
    # automatically — autogenerate only detects column/table changes, not
    # enum-label changes, so these have to be added explicitly.
    #
    # Kept in their own revision, ahead of the migration that first stores
    # one of these labels: Postgres will not let a newly added enum value be
    # used in the same transaction that added it.
    #
    # Purely additive — no existing row's role or notification type changes,
    # and no account becomes HR as a result of this migration. HR accounts
    # are created afterwards through the normal user-management flow.
    op.execute("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'HR' AFTER 'OPERATIONAL_MANAGER'")

    op.execute("ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS 'TASK_QUERY' AFTER 'ASSIGNED_TASK'")


def downgrade():
    # Postgres does not support dropping a value from an enum type.
    # Downgrading is a no-op; a real revert would mean recreating both types
    # without these labels and rewriting every dependent column.
    pass
