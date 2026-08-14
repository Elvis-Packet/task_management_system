"""add task_queries table

Revision ID: d5e9c04f7a22
Revises: c3f7a2b81d45
Create Date: 2026-08-14 10:07:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'd5e9c04f7a22'
down_revision = 'c3f7a2b81d45'
branch_labels = None
depends_on = None


def upgrade():
    """A manager's status request against one incomplete task, plus the staff
    member's answer.

    Purely additive — a brand new table and a brand new enum type. No
    existing table is altered and no existing row is touched, so this is
    non-destructive and safe to run against live data.

    The task_id foreign key is ON DELETE CASCADE: a query is meaningless
    without the task it asks about, unlike task_exceptions, which is a
    manager's own record and outlives edits to the task."""

    # Created explicitly, then referenced with create_type=False below —
    # otherwise create_table() emits a second CREATE TYPE for the same enum
    # and the migration fails on "type querystatus already exists".
    query_status = postgresql.ENUM('OPEN', 'ANSWERED', 'CLOSED', name='querystatus')
    query_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        'task_queries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('task_id', sa.Integer(), nullable=False),
        sa.Column('manager_id', sa.Integer(), nullable=False),
        sa.Column('employee_id', sa.Integer(), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column(
            'status',
            postgresql.ENUM('OPEN', 'ANSWERED', 'CLOSED', name='querystatus', create_type=False),
            nullable=False,
            server_default='OPEN',
        ),
        sa.Column('task_status_at_query', sa.String(length=30), nullable=True),
        sa.Column('response', sa.Text(), nullable=True),
        sa.Column('responded_at', sa.DateTime(), nullable=True),
        sa.Column('closed_by', sa.Integer(), nullable=True),
        sa.Column('closed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['task_id'], ['assigned_tasks.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['manager_id'], ['users.id']),
        sa.ForeignKeyConstraint(['employee_id'], ['users.id']),
        sa.ForeignKeyConstraint(['closed_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_index('ix_task_queries_task_id', 'task_queries', ['task_id'])
    op.create_index('ix_task_queries_manager_id', 'task_queries', ['manager_id'])
    op.create_index('ix_task_queries_employee_id', 'task_queries', ['employee_id'])
    op.create_index('ix_task_queries_created_at', 'task_queries', ['created_at'])

    # Composite indexes for the two hot paths: a task's own query thread, and
    # "how many unanswered queries does this employee have" — the latter runs
    # once per HR dashboard load across every employee.
    op.create_index('idx_task_query_task_status', 'task_queries', ['task_id', 'status'])
    op.create_index('idx_task_query_employee_status', 'task_queries', ['employee_id', 'status'])


def downgrade():
    op.drop_index('idx_task_query_employee_status', table_name='task_queries')
    op.drop_index('idx_task_query_task_status', table_name='task_queries')
    op.drop_index('ix_task_queries_created_at', table_name='task_queries')
    op.drop_index('ix_task_queries_employee_id', table_name='task_queries')
    op.drop_index('ix_task_queries_manager_id', table_name='task_queries')
    op.drop_index('ix_task_queries_task_id', table_name='task_queries')

    op.drop_table('task_queries')

    sa.Enum(name='querystatus').drop(op.get_bind(), checkfirst=True)
