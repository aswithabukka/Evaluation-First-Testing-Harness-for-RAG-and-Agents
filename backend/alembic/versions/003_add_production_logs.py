"""Add production_logs table for production traffic ingestion

Revision ID: 003
Revises: 002
Create Date: 2026-02-23 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "production_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source", sa.String(255), nullable=False, index=True),
        sa.Column("pipeline_version", sa.String(100), nullable=True),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("contexts", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("tool_calls", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("user_feedback", sa.String(50), nullable=True),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("is_error", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "status",
            sa.Enum("received", "sampled", "skipped", "evaluated", name="ingestionstatus"),
            nullable=False,
            server_default="received",
            index=True,
        ),
        sa.Column(
            "sampled_into_test_set_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("test_sets.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "sampled_into_test_case_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("test_cases.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "evaluation_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("evaluation_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("produced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("sampled_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Index for sampling queries: find un-sampled entries by source
    op.create_index(
        "ix_production_logs_source_status",
        "production_logs",
        ["source", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_production_logs_source_status", table_name="production_logs")
    op.drop_table("production_logs")
    op.execute("DROP TYPE IF EXISTS ingestionstatus")
