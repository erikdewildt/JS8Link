"""add structured diagnostic traces

Revision ID: 0032_diagnostic_traces
Revises: 0031_monitor_map_greyline
"""

import sqlalchemy as sa

from alembic import op

revision = "0032_diagnostic_traces"
down_revision = "0031_monitor_map_greyline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "app_config",
        sa.Column("diagnostics_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "app_config",
        sa.Column("diagnostics_retention_days", sa.Integer(), nullable=False, server_default="7"),
    )
    op.create_table(
        "diagnostic_traces",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("trace_id", sa.String(length=36), nullable=False, unique=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False, server_default="info"),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("raw_payload", sa.Text(), nullable=True),
        sa.Column("interpretation", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_diagnostic_traces_trace_id", "diagnostic_traces", ["trace_id"])
    op.create_index("ix_diagnostic_traces_source", "diagnostic_traces", ["source"])
    op.create_index("ix_diagnostic_traces_event_type", "diagnostic_traces", ["event_type"])
    op.create_index("ix_diagnostic_traces_severity", "diagnostic_traces", ["severity"])
    op.create_index("ix_diagnostic_traces_created_at", "diagnostic_traces", ["created_at"])
    op.create_table(
        "diagnostic_processing",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("trace_id", sa.String(length=36), sa.ForeignKey("diagnostic_traces.trace_id"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("operation", sa.String(length=128), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=False, server_default="ok"),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_diagnostic_processing_trace_id", "diagnostic_processing", ["trace_id"])


def downgrade() -> None:
    op.drop_index("ix_diagnostic_processing_trace_id", table_name="diagnostic_processing")
    op.drop_table("diagnostic_processing")
    for name in (
        "ix_diagnostic_traces_created_at",
        "ix_diagnostic_traces_severity",
        "ix_diagnostic_traces_event_type",
        "ix_diagnostic_traces_source",
        "ix_diagnostic_traces_trace_id",
    ):
        op.drop_index(name, table_name="diagnostic_traces")
    op.drop_table("diagnostic_traces")
    op.drop_column("app_config", "diagnostics_retention_days")
    op.drop_column("app_config", "diagnostics_enabled")
