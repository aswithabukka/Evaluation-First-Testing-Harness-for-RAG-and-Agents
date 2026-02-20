"""Initial schema

Revision ID: 001
Revises:
Create Date: 2025-01-01 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── test_sets ──────────────────────────────────────────────────────────────
    op.create_table(
        "test_sets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("version", sa.String(50), nullable=False, server_default="1.0"),
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
    )
    op.create_index("ix_test_sets_name", "test_sets", ["name"])

    # ── test_cases ─────────────────────────────────────────────────────────────
    op.create_table(
        "test_cases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "test_set_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("test_sets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("query", sa.Text, nullable=False),
        sa.Column("expected_output", sa.Text, nullable=True),
        sa.Column("ground_truth", sa.Text, nullable=True),
        sa.Column("context", postgresql.JSONB, nullable=True),
        sa.Column("failure_rules", postgresql.JSONB, nullable=True),
        sa.Column("tags", postgresql.JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_test_cases_test_set_id", "test_cases", ["test_set_id"])

    # ── evaluation_runs ────────────────────────────────────────────────────────
    op.create_table(
        "evaluation_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "test_set_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("test_sets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("pipeline_version", sa.String(100), nullable=True),
        sa.Column("git_commit_sha", sa.String(40), nullable=True),
        sa.Column("git_branch", sa.String(255), nullable=True),
        sa.Column("git_pr_number", sa.String(20), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "running",
                "completed",
                "failed",
                "gate_blocked",
                name="runstatus",
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("triggered_by", sa.String(50), nullable=False, server_default="manual"),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("overall_passed", sa.Boolean, nullable=True),
        sa.Column("gate_threshold_snapshot", postgresql.JSONB, nullable=True),
        sa.Column("summary_metrics", postgresql.JSONB, nullable=True),
    )
    op.create_index("ix_evaluation_runs_test_set_id", "evaluation_runs", ["test_set_id"])
    op.create_index("ix_evaluation_runs_git_commit", "evaluation_runs", ["git_commit_sha"])
    op.create_index("ix_evaluation_runs_status", "evaluation_runs", ["status"])
    op.create_index(
        "ix_evaluation_runs_test_set_status",
        "evaluation_runs",
        ["test_set_id", "status"],
    )

    # ── evaluation_results ─────────────────────────────────────────────────────
    op.create_table(
        "evaluation_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("evaluation_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "test_case_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("test_cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("faithfulness", sa.Float, nullable=True),
        sa.Column("answer_relevancy", sa.Float, nullable=True),
        sa.Column("context_precision", sa.Float, nullable=True),
        sa.Column("context_recall", sa.Float, nullable=True),
        sa.Column("rules_passed", sa.Boolean, nullable=True),
        sa.Column("rules_detail", postgresql.JSONB, nullable=True),
        sa.Column("llm_judge_score", sa.Float, nullable=True),
        sa.Column("llm_judge_reasoning", sa.Text, nullable=True),
        sa.Column("passed", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("failure_reason", sa.Text, nullable=True),
        sa.Column("raw_output", sa.Text, nullable=True),
        sa.Column("raw_contexts", postgresql.JSONB, nullable=True),
        sa.Column("tool_calls", postgresql.JSONB, nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.Column(
            "evaluated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_evaluation_results_run_id", "evaluation_results", ["run_id"])
    op.create_index(
        "ix_evaluation_results_test_case_id", "evaluation_results", ["test_case_id"]
    )
    op.create_index(
        "ix_evaluation_results_passed", "evaluation_results", ["run_id", "passed"]
    )

    # ── metrics_history ────────────────────────────────────────────────────────
    op.create_table(
        "metrics_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "test_set_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("test_sets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("evaluation_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("metric_name", sa.String(100), nullable=False),
        sa.Column("metric_value", sa.Float, nullable=False),
        sa.Column("pipeline_version", sa.String(100), nullable=True),
        sa.Column("git_commit_sha", sa.String(40), nullable=True),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_metrics_history_trend",
        "metrics_history",
        ["test_set_id", "metric_name", "recorded_at"],
    )


def downgrade() -> None:
    op.drop_table("metrics_history")
    op.drop_index("ix_evaluation_results_passed", "evaluation_results")
    op.drop_index("ix_evaluation_results_test_case_id", "evaluation_results")
    op.drop_index("ix_evaluation_results_run_id", "evaluation_results")
    op.drop_table("evaluation_results")
    op.drop_index("ix_evaluation_runs_test_set_status", "evaluation_runs")
    op.drop_index("ix_evaluation_runs_status", "evaluation_runs")
    op.drop_index("ix_evaluation_runs_git_commit", "evaluation_runs")
    op.drop_index("ix_evaluation_runs_test_set_id", "evaluation_runs")
    op.drop_table("evaluation_runs")
    op.execute("DROP TYPE IF EXISTS runstatus")
    op.drop_index("ix_test_cases_test_set_id", "test_cases")
    op.drop_table("test_cases")
    op.drop_index("ix_test_sets_name", "test_sets")
    op.drop_table("test_sets")
