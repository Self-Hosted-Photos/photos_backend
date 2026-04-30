"""media, albums, album_media, shares tables

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-23
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── media ─────────────────────────────────────────────────────────────────
    op.create_table(
        "media",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("filename_original", sa.String(1024), nullable=False),
        sa.Column("filename_stored", sa.String(255), nullable=False),
        sa.Column(
            "media_type",
            sa.Enum("photo", "video", name="media_type"),
            nullable=False,
        ),
        sa.Column("mime_type", sa.String(127), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger, nullable=False),
        sa.Column(
            "status",
            sa.Enum("uploading", "processing", "ready", "failed", name="media_status"),
            nullable=False,
            server_default="uploading",
        ),
        sa.Column("original_path", sa.String(1024), nullable=False),
        sa.Column("transcoded_path", sa.String(1024), nullable=True),
        sa.Column("thumbnail_path", sa.String(1024), nullable=True),
        sa.Column("exif_data", sa.JSON, nullable=True),
        sa.Column("captured_at", sa.Date, nullable=True),
        sa.Column("latitude", sa.Float, nullable=True),
        sa.Column("longitude", sa.Float, nullable=True),
        sa.Column("location_display_name", sa.String(512), nullable=True),
        sa.Column(
            "uploaded_at",
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
    op.create_index("idx_media_owner_date", "media", ["owner_id", "captured_at"])
    op.create_index("idx_media_status", "media", ["status"])
    # Partial index — only rows that have GPS data (avoids indexing NULLs)
    op.create_index(
        "idx_media_owner_location",
        "media",
        ["owner_id", "latitude", "longitude"],
        postgresql_where=sa.text("latitude IS NOT NULL AND longitude IS NOT NULL"),
    )

    # ── albums ────────────────────────────────────────────────────────────────
    op.create_table(
        "albums",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.String(2048), nullable=True),
        sa.Column(
            "cover_media_id",
            UUID(as_uuid=True),
            sa.ForeignKey("media.id", ondelete="SET NULL"),
            nullable=True,
        ),
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
    op.create_index("idx_albums_owner", "albums", ["owner_id"])

    # ── album_media ───────────────────────────────────────────────────────────
    op.create_table(
        "album_media",
        sa.Column(
            "album_id",
            UUID(as_uuid=True),
            sa.ForeignKey("albums.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "media_id",
            UUID(as_uuid=True),
            sa.ForeignKey("media.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "added_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # ── shares ────────────────────────────────────────────────────────────────
    op.create_table(
        "shares",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "share_type",
            sa.Enum("user", "album", "public_link", name="share_type"),
            nullable=False,
        ),
        sa.Column(
            "target_media_id",
            UUID(as_uuid=True),
            sa.ForeignKey("media.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "target_album_id",
            UUID(as_uuid=True),
            sa.ForeignKey("albums.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "shared_with_user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("public_token", sa.String(255), nullable=True),
        sa.Column("permission", sa.String(50), nullable=False, server_default="view"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "idx_shares_public_token",
        "shares",
        ["public_token"],
        unique=True,
        postgresql_where=sa.text("public_token IS NOT NULL"),
    )
    op.create_index("idx_shares_shared_with", "shares", ["shared_with_user_id"])


def downgrade() -> None:
    op.drop_table("shares")
    op.drop_table("album_media")
    op.drop_table("albums")
    op.drop_table("media")
    op.execute("DROP TYPE IF EXISTS share_type")
    op.execute("DROP TYPE IF EXISTS media_status")
    op.execute("DROP TYPE IF EXISTS media_type")
