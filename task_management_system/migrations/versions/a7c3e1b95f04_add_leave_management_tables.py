"""add leave_types, leave_requests and leave_attachments

Revision ID: a7c3e1b95f04
Revises: f1a2b3c4d5e6
Create Date: 2026-09-04 09:05:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'a7c3e1b95f04'
down_revision = 'f1a2b3c4d5e6'
branch_labels = None
depends_on = None


def upgrade():
    """Leave Management.

    Purely additive — three brand new tables and one brand new enum type. No
    existing table is altered, no existing column is dropped or retyped, and
    no existing row is read or written. Users, departments, tasks, plans,
    notifications and audit logs are untouched, so this is safe to run
    against live data.

    Foreign keys are deliberately asymmetric:
      * leave_attachments -> leave_requests is ON DELETE CASCADE, because a
        supporting document has no meaning without the application it
        supports;
      * every users.id reference is a plain restricting FK, so an employee
        with leave history cannot be hard-deleted out from under it. The
        application soft-deletes users (users.deleted_at) anyway, which
        leaves the history intact and readable.
    """

    # Created explicitly, then referenced with create_type=False below —
    # otherwise create_table() emits a second CREATE TYPE for the same enum
    # and the migration fails on "type leavestatus already exists".
    leave_status = postgresql.ENUM(
        'PENDING', 'APPROVED', 'REJECTED', 'CANCELLED', name='leavestatus'
    )
    leave_status.create(op.get_bind(), checkfirst=True)

    # ------------------------------------------------------------------
    # leave_types — the catalogue, plus the per-type policy knobs. Seeded
    # from the company's own form by app.create_seed_leave_types(), then
    # owned by HR through the API.
    # ------------------------------------------------------------------
    op.create_table(
        'leave_types',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=80), nullable=False),
        sa.Column('code', sa.String(length=30), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('requires_attachment', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('allows_backdating', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('min_notice_days', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('entitlement_days', sa.Integer(), nullable=True),
        sa.Column('is_paid', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
        sa.UniqueConstraint('code'),
    )

    op.create_index('ix_leave_types_code', 'leave_types', ['code'])

    # ------------------------------------------------------------------
    # leave_requests — one row per application, mirroring the five sections
    # of the paper form. Employee information is NOT copied onto this row;
    # it is read through employee_id, so a department transfer never
    # rewrites somebody's leave history.
    # ------------------------------------------------------------------
    op.create_table(
        'leave_requests',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('employee_id', sa.Integer(), nullable=False),
        sa.Column('leave_type_id', sa.Integer(), nullable=False),

        # Section 2 — leave details
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=False),
        # Numeric, not Integer: the form has a "Half Day? Yes/No" box, and
        # 0.5 is the honest value for it.
        sa.Column('days', sa.Numeric(precision=5, scale=1), nullable=False),
        sa.Column('is_half_day', sa.Boolean(), nullable=False, server_default=sa.false()),

        # Section 3 — reason
        sa.Column('reason', sa.Text(), nullable=False),

        # Section 4 — contact during leave
        sa.Column('contact_phone', sa.String(length=30), nullable=True),
        sa.Column('contact_address', sa.String(length=255), nullable=True),
        sa.Column('handover_to_id', sa.Integer(), nullable=True),
        sa.Column('handover_contact', sa.String(length=30), nullable=True),

        # Lifecycle
        sa.Column(
            'status',
            postgresql.ENUM(
                'PENDING', 'APPROVED', 'REJECTED', 'CANCELLED',
                name='leavestatus', create_type=False,
            ),
            nullable=False,
            server_default='PENDING',
        ),
        sa.Column('submitted_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),

        # Section 5 — authorization
        sa.Column('reviewed_by', sa.Integer(), nullable=True),
        sa.Column('reviewer_role', sa.String(length=30), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(), nullable=True),
        sa.Column('review_comment', sa.Text(), nullable=True),

        # Withdrawal — kept separate from rejection so the record never
        # confuses "I changed my mind" with "this was refused".
        sa.Column('cancelled_at', sa.DateTime(), nullable=True),
        sa.Column('cancelled_by', sa.Integer(), nullable=True),
        sa.Column('cancellation_reason', sa.Text(), nullable=True),

        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),

        sa.ForeignKeyConstraint(['employee_id'], ['users.id']),
        sa.ForeignKeyConstraint(['leave_type_id'], ['leave_types.id']),
        sa.ForeignKeyConstraint(['handover_to_id'], ['users.id']),
        sa.ForeignKeyConstraint(['reviewed_by'], ['users.id']),
        sa.ForeignKeyConstraint(['cancelled_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_index('ix_leave_requests_employee_id', 'leave_requests', ['employee_id'])
    op.create_index('ix_leave_requests_leave_type_id', 'leave_requests', ['leave_type_id'])
    op.create_index('ix_leave_requests_status', 'leave_requests', ['status'])
    op.create_index('ix_leave_requests_created_at', 'leave_requests', ['created_at'])

    # The three hot paths: an employee's own history and the overlap check
    # (employee + status), any date-range view, and "who is on leave right
    # now" across the organization (status + start_date).
    op.create_index(
        'idx_leave_request_employee_status', 'leave_requests', ['employee_id', 'status']
    )
    op.create_index('idx_leave_request_dates', 'leave_requests', ['start_date', 'end_date'])
    op.create_index('idx_leave_request_status_start', 'leave_requests', ['status', 'start_date'])

    # ------------------------------------------------------------------
    # leave_attachments — supporting documents, in their own table so that
    # listing or filtering leave never loads a byte of file content.
    # ------------------------------------------------------------------
    op.create_table(
        'leave_attachments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('leave_request_id', sa.Integer(), nullable=False),
        sa.Column('file_name', sa.String(length=255), nullable=False),
        sa.Column('content_type', sa.String(length=120), nullable=False),
        sa.Column('file_size', sa.Integer(), nullable=False),
        sa.Column('content', sa.LargeBinary(), nullable=False),
        sa.Column('uploaded_by', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ['leave_request_id'], ['leave_requests.id'], ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(['uploaded_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_index(
        'ix_leave_attachments_leave_request_id', 'leave_attachments', ['leave_request_id']
    )


def downgrade():
    op.drop_index('ix_leave_attachments_leave_request_id', table_name='leave_attachments')
    op.drop_table('leave_attachments')

    op.drop_index('idx_leave_request_status_start', table_name='leave_requests')
    op.drop_index('idx_leave_request_dates', table_name='leave_requests')
    op.drop_index('idx_leave_request_employee_status', table_name='leave_requests')
    op.drop_index('ix_leave_requests_created_at', table_name='leave_requests')
    op.drop_index('ix_leave_requests_status', table_name='leave_requests')
    op.drop_index('ix_leave_requests_leave_type_id', table_name='leave_requests')
    op.drop_index('ix_leave_requests_employee_id', table_name='leave_requests')
    op.drop_table('leave_requests')

    op.drop_index('ix_leave_types_code', table_name='leave_types')
    op.drop_table('leave_types')

    sa.Enum(name='leavestatus').drop(op.get_bind(), checkfirst=True)
