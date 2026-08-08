"""persist monitor map center and zoom

Revision ID: 0017_monitor_map_viewport
Revises: 0016_transmitted_message_radio_context
"""

import sqlalchemy as sa

from alembic import op

revision = "0017_monitor_map_viewport"
down_revision = "0016_transmitted_message_radio_context"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "app_config",
        sa.Column("monitor_map_center_latitude", sa.Float(), nullable=False, server_default="52"),
    )
    op.add_column(
        "app_config",
        sa.Column("monitor_map_center_longitude", sa.Float(), nullable=False, server_default="5"),
    )
    op.add_column(
        "app_config",
        sa.Column("monitor_map_zoom", sa.Float(), nullable=False, server_default="3"),
    )


def downgrade() -> None:
    op.drop_column("app_config", "monitor_map_zoom")
    op.drop_column("app_config", "monitor_map_center_longitude")
    op.drop_column("app_config", "monitor_map_center_latitude")
