"""initial users, email_tokens, refresh_tokens

Revision ID: 0001
Revises:
Create Date: 2026-04-21
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── users ─────────────────────────────────────────────────────────────────
    # sa.Enum with create_type=True (default) — SQLAlchemy creates the PG enum
    # type automatically as part of CREATE TABLE. Do NOT also call
    # op.execute("CREATE TYPE ...") — that causes a duplicate in SQLAlchemy 2.x.
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=True),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("avatar_url", sa.String(2048), nullable=True),
        sa.Column("oauth_provider", sa.String(50), nullable=True),
        sa.Column("oauth_sub", sa.String(255), nullable=True),
        sa.Column(
            "role",
            sa.Enum("user", "admin", name="user_role"),
            nullable=False,
            server_default="user",
        ),
        sa.Column(
            "status",
            sa.Enum("pending", "active", "suspended", name="user_status"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("storage_used_bytes", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column(
            "storage_quota_bytes",
            sa.BigInteger,
            nullable=False,
            server_default=str(10 * 1024 * 1024 * 1024),
        ),
        sa.Column("email_verified", sa.Boolean, nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("idx_users_email", "users", ["email"], unique=True)
    op.create_index("idx_users_oauth", "users", ["oauth_provider", "oauth_sub"])
    op.create_index("idx_users_status", "users", ["status"])

    # ── email_tokens ──────────────────────────────────────────────────────────
    op.create_table(
        "email_tokens",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token", sa.String(255), nullable=False),
        sa.Column(
            "type",
            sa.Enum("verification", "password_reset", name="email_token_type"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used", sa.Boolean, nullable=False, server_default="false"),
    )
    op.create_index("idx_email_tokens_token", "email_tokens", ["token"], unique=True)

    # ── refresh_tokens ────────────────────────────────────────────────────────
    op.create_table(
        "refresh_tokens",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(255), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("user_agent", sa.String(512), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("idx_refresh_tokens_hash", "refresh_tokens", ["token_hash"], unique=True)


def downgrade() -> None:
    op.drop_table("refresh_tokens")
    op.drop_table("email_tokens")
    op.drop_table("users")
    op.execute("DROP TYPE IF EXISTS email_token_type")
    op.execute("DROP TYPE IF EXISTS user_status")
    op.execute("DROP TYPE IF EXISTS user_role")
