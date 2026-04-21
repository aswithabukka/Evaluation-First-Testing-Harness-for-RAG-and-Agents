"""Add manifest, manifest_fingerprint, budget_summary to evaluation_runs.

Revision ID: 005
Revises: 004
Create Date: 2026-04-21 00:00:00.000000

The ``manifest`` column snapshots evaluator versions, LLM prompt hashes,
seeds, and library versions — produced by ``runner.manifest.Manifest`` in
the Celery worker. ``manifest_fingerprint`` is a stable 16-char hash of the
manifest (excluding ``sealed_at``) for quick "same config?" lookups. The
``budget_summary`` column stores the cost + latency budget outcome from
``runner.budget.Budget.summary()``.

All three columns are nullable so historical runs without them continue to
work.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "evaluation_runs",
        sa.Column("manifest", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "evaluation_runs",
        sa.Column("manifest_fingerprint", sa.String(length=32), nullable=True),
    )
    op.create_index(
        "ix_evaluation_runs_manifest_fingerprint",
        "evaluation_runs",
        ["manifest_fingerprint"],
    )
    op.add_column(
        "evaluation_runs",
        sa.Column("budget_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_index("ix_evaluation_runs_manifest_fingerprint", table_name="evaluation_runs")
    op.drop_column("evaluation_runs", "budget_summary")
    op.drop_column("evaluation_runs", "manifest_fingerprint")
    op.drop_column("evaluation_runs", "manifest")
