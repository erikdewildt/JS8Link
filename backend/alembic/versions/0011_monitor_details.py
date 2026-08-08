"""store mode and last-heard radio details

Revision ID: 0011_monitor_details
Revises: 0010_ui_preferences
"""

import sqlalchemy as sa

from alembic import op

revision = "0011_monitor_details"
down_revision = "0010_ui_preferences"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("received_messages", sa.Column("mode", sa.String(32)))
    op.add_column("stations", sa.Column("last_offset", sa.Integer()))
    op.add_column("stations", sa.Column("last_mode", sa.String(32)))
    op.add_column("app_config", sa.Column("monitor_view", sa.String(16), nullable=False, server_default="messages"))


def downgrade() -> None:
    op.drop_column("stations", "last_mode")
    op.drop_column("stations", "last_offset")
    op.drop_column("received_messages", "mode")
    op.drop_column("app_config", "monitor_view")
