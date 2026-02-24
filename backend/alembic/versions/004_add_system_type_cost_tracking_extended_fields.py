"""Add system_type to test_sets, cost tracking, and extended test_case fields

Revision ID: 004
Revises: 003
Create Date: 2026-02-23 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create system_type enum
    system_type_enum = sa.Enum(
        "rag", "agent", "chatbot", "code_gen", "search",
        "classification", "summarization", "translation", "custom",
        name="systemtype",
    )
    system_type_enum.create(op.get_bind(), checkfirst=True)

    # Add system_type to test_sets
    op.add_column(
        "test_sets",
        sa.Column(
            "system_type",
            system_type_enum,
            nullable=False,
            server_default="rag",
        ),
    )
    op.create_index("ix_test_sets_system_type", "test_sets", ["system_type"])

    # Add extended fields to test_cases
    op.add_column(
        "test_cases",
        sa.Column("expected_labels", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "test_cases",
        sa.Column("expected_ranking", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "test_cases",
        sa.Column("conversation_turns", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    # Add cost tracking to evaluation_results
    op.add_column(
        "evaluation_results",
        sa.Column("eval_cost_usd", sa.Float(), nullable=True),
    )
    op.add_column(
        "evaluation_results",
        sa.Column("tokens_used", sa.Integer(), nullable=True),
    )
    op.add_column(
        "evaluation_results",
        sa.Column("extended_metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    # Add cost tracking to evaluation_runs
    op.add_column(
        "evaluation_runs",
        sa.Column("total_cost_usd", sa.Float(), nullable=True),
    )
    op.add_column(
        "evaluation_runs",
        sa.Column("total_tokens", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("evaluation_runs", "total_tokens")
    op.drop_column("evaluation_runs", "total_cost_usd")
    op.drop_column("evaluation_results", "extended_metrics")
    op.drop_column("evaluation_results", "tokens_used")
    op.drop_column("evaluation_results", "eval_cost_usd")
    op.drop_column("test_cases", "conversation_turns")
    op.drop_column("test_cases", "expected_ranking")
    op.drop_column("test_cases", "expected_labels")
    op.drop_index("ix_test_sets_system_type", table_name="test_sets")
    op.drop_column("test_sets", "system_type")
    op.execute("DROP TYPE IF EXISTS systemtype")
