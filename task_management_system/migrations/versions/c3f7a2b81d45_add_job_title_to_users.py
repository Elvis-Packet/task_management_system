"""add job_title to users

Revision ID: c3f7a2b81d45
Revises: b7c1d94a2e10
Create Date: 2026-08-14 10:06:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c3f7a2b81d45'
down_revision = 'b7c1d94a2e10'
branch_labels = None
depends_on = None


def upgrade():
    # The person's position within their department ("Financial Analyst"),
    # distinct from `role`, which is the system permission level.
    #
    # Nullable and with no default: every existing account simply carries no
    # job title until somebody sets one, so this adds a column without
    # touching a single existing row's data. The UI has always rendered
    # `user.title` — it was just never populated by the API.
    op.add_column('users', sa.Column('job_title', sa.String(length=120), nullable=True))


def downgrade():
    op.drop_column('users', 'job_title')
