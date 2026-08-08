"""add monitor_map_cluster_stations

Revision ID: 59d120930007
Revises: f148dcef473d
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "59d120930007"
down_revision: str | None = "f148dcef473d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "app_config",
        sa.Column("monitor_map_cluster_stations", sa.Boolean(), nullable=False, server_default=sa.text("1")),
    )


def downgrade() -> None:
    op.drop_column("app_config", "monitor_map_cluster_stations")
