"""Add jobs table.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-03

Creates the jobs table and associated indexes for the CrowdGPU Job & Scheduler system.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # -----------------------------------------------------------------
    # Table: jobs
    # -----------------------------------------------------------------
    op.create_table(
        "jobs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("command", sa.Text(), nullable=False),
        sa.Column(
            "requirements",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default="QUEUED",
            nullable=False,
        ),
        sa.Column("assigned_peer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
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
            name=op.f("fk_jobs_owner_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["assigned_peer_id"],
            ["peers.id"],
            name=op.f("fk_jobs_assigned_peer_id_peers"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_jobs")),
    )

    op.create_index(op.f("ix_jobs_owner_id"), "jobs", ["owner_id"], unique=False)
    op.create_index(op.f("ix_jobs_status"), "jobs", ["status"], unique=False)
    op.create_index(
        op.f("ix_jobs_assigned_peer_id"), "jobs", ["assigned_peer_id"], unique=False
    )
    op.create_index(
        "ix_jobs_owner_created", "jobs", ["owner_id", "created_at"], unique=False
    )
    op.create_index(
        "ix_jobs_status_created", "jobs", ["status", "created_at"], unique=False
    )
    op.create_index(
        "ix_jobs_assigned_peer_status",
        "jobs",
        ["assigned_peer_id", "status"],
        unique=False,
    )
    op.create_index(
        "uq_jobs_assigned_peer_active",
        "jobs",
        ["assigned_peer_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('ASSIGNED', 'RUNNING')"),
    )


def downgrade() -> None:
    op.drop_index("uq_jobs_assigned_peer_active", table_name="jobs")
    op.drop_index("ix_jobs_assigned_peer_status", table_name="jobs")
    op.drop_index("ix_jobs_status_created", table_name="jobs")
    op.drop_index("ix_jobs_owner_created", table_name="jobs")
    op.drop_index(op.f("ix_jobs_assigned_peer_id"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_status"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_owner_id"), table_name="jobs")
    op.drop_table("jobs")
