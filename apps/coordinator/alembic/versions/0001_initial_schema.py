"""Initial schema — users, peers, gpu_capabilities.

Revision ID: 0001
Revises:
Create Date: 2026-09-16

This migration creates the three foundational tables for peer registration.
No business tables (jobs, sessions, accounting, reputation) are included —
those belong to later phases per the project task constraints.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # -----------------------------------------------------------------
    # Table: users
    # -----------------------------------------------------------------
    op.create_table(
        "users",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)

    # -----------------------------------------------------------------
    # Table: peers
    # -----------------------------------------------------------------
    op.create_table(
        "peers",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("hostname", sa.String(length=255), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default="offline",
            nullable=False,
        ),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name=op.f("fk_peers_owner_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_peers")),
    )
    op.create_index(op.f("ix_peers_owner_id"), "peers", ["owner_id"], unique=False)

    # -----------------------------------------------------------------
    # Table: gpu_capabilities
    # -----------------------------------------------------------------
    op.create_table(
        "gpu_capabilities",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("peer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("gpu_name", sa.String(length=255), nullable=False),
        sa.Column("vram_mb", sa.Integer(), nullable=False),
        sa.Column("driver_version", sa.String(length=64), nullable=True),
        sa.Column("cuda_version", sa.String(length=32), nullable=True),
        sa.Column("compute_capability", sa.String(length=16), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["peer_id"],
            ["peers.id"],
            name=op.f("fk_gpu_capabilities_peer_id_peers"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_gpu_capabilities")),
    )
    op.create_index(
        op.f("ix_gpu_capabilities_peer_id"),
        "gpu_capabilities",
        ["peer_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_gpu_capabilities_peer_id"), table_name="gpu_capabilities")
    op.drop_table("gpu_capabilities")
    op.drop_index(op.f("ix_peers_owner_id"), table_name="peers")
    op.drop_table("peers")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
