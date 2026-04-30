"""add deleted user status

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-30
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE user_status ADD VALUE IF NOT EXISTS 'deleted'")


def downgrade() -> None:
    # PostgreSQL cannot remove enum values once added; this is intentional.
    pass
