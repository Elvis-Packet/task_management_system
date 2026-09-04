"""add LEAVE_REQUEST to notificationtype and commenttargettype

Revision ID: f1a2b3c4d5e6
Revises: d5e9c04f7a22
Create Date: 2026-09-04 09:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f1a2b3c4d5e6'
down_revision = 'd5e9c04f7a22'
branch_labels = None
depends_on = None


def upgrade():
    # Postgres native enum types don't pick up new Python Enum members
    # automatically, and a newly added enum value cannot be USED in the same
    # transaction that added it — so, exactly as b7c1d94a2e10 did for HR and
    # TASK_QUERY, the label additions get their own revision ahead of the
    # migration that first stores one.
    #
    # Purely additive: no existing row's notification type or audit target
    # type changes, and nothing starts referring to these labels until the
    # next revision creates the leave tables.
    op.execute(
        "ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS 'LEAVE_REQUEST' AFTER 'COMMENT'"
    )

    # audit_logs.target_type reuses CommentTargetType, so a leave decision can
    # be linked to the leave request it was about and show up in that
    # request's timeline the same way task audit rows already do.
    op.execute(
        "ALTER TYPE commenttargettype ADD VALUE IF NOT EXISTS 'LEAVE_REQUEST' AFTER 'ACTIVITY'"
    )


def downgrade():
    # Postgres does not support dropping a value from an enum type.
    # Downgrading is a no-op; a real revert would mean recreating both types
    # without these labels and rewriting every dependent column.
    pass
