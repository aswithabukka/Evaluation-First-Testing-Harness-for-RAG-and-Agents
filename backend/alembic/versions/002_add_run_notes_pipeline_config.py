"""Add notes and pipeline_config to evaluation_runs

Revision ID: 002
Revises: 001
Create Date: 2026-02-20 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "evaluation_runs",
        sa.Column("notes", sa.Text(), nullable=True),
    )
    op.add_column(
        "evaluation_runs",
        sa.Column("pipeline_config", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("evaluation_runs", "pipeline_config")
    op.drop_column("evaluation_runs", "notes")
