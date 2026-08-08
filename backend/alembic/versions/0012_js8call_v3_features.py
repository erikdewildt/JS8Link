"""add js8call version, tdrift, tx tracking, heartbeat offset

Revision ID: 0012_js8call_v3_features
Revises: 0011_monitor_details
"""

import sqlalchemy as sa

from alembic import op

revision = "0012_js8call_v3_features"
down_revision = "0011_monitor_details"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("app_config", sa.Column("js8call_version", sa.String(32), nullable=True))
    op.add_column(
        "app_config", sa.Column("heartbeat_offset_mode", sa.String(16), nullable=False, server_default="auto")
    )
    op.add_column("app_config", sa.Column("fixed_heartbeat_offset", sa.Integer(), nullable=False, server_default="800"))
    op.add_column("received_messages", sa.Column("tdrift", sa.Float(), nullable=True))
    op.add_column("stations", sa.Column("last_tdrift", sa.Float(), nullable=True))
    op.add_column("transmitted_messages", sa.Column("tx_frame_type", sa.String(32), nullable=True))
    op.add_column("transmitted_messages", sa.Column("confirmed_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("transmitted_messages", "confirmed_at")
    op.drop_column("transmitted_messages", "tx_frame_type")
    op.drop_column("stations", "last_tdrift")
    op.drop_column("received_messages", "tdrift")
    op.drop_column("app_config", "fixed_heartbeat_offset")
    op.drop_column("app_config", "heartbeat_offset_mode")
    op.drop_column("app_config", "js8call_version")
