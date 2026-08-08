"""add station information query enable setting

Revision ID: 0025_station_queries_enabled
Revises: 0024_monitor_map_popups
"""

import sqlalchemy as sa

from alembic import op

revision = "0025_station_queries_enabled"
down_revision = "0024_monitor_map_popups"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "app_config",
        sa.Column("station_queries_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column("app_config", "station_queries_enabled")
