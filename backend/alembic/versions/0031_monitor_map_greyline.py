"""add greyline map preference

Revision ID: 0031_monitor_map_greyline
Revises: 0030_time_display
"""

import sqlalchemy as sa

from alembic import op

revision = "0031_monitor_map_greyline"
down_revision = "0030_time_display"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "app_config",
        sa.Column("monitor_map_greyline", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column("app_config", "monitor_map_greyline")
