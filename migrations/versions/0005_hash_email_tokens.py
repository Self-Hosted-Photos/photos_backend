"""hash email tokens

Rename email_tokens.token → token_hash to reflect that the column now stores
SHA-256 digests of the raw token. The raw token is sent in the email only and
never persisted. Matches the pattern already applied to refresh_tokens.

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-13
"""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("idx_email_tokens_token", table_name="email_tokens")
    op.alter_column("email_tokens", "token", new_column_name="token_hash")
    op.create_index("idx_email_tokens_token_hash", "email_tokens", ["token_hash"], unique=True)


def downgrade() -> None:
    op.drop_index("idx_email_tokens_token_hash", table_name="email_tokens")
    op.alter_column("email_tokens", "token_hash", new_column_name="token")
    op.create_index("idx_email_tokens_token", "email_tokens", ["token"], unique=True)
