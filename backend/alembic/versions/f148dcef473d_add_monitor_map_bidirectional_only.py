"""add monitor_map_bidirectional_only

Revision ID: f148dcef473d
Revises: 0032_diagnostic_traces
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f148dcef473d"
down_revision: str | None = "0032_diagnostic_traces"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "app_config",
        sa.Column("monitor_map_bidirectional_only", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    )


def downgrade() -> None:
    op.drop_column("app_config", "monitor_map_bidirectional_only")
