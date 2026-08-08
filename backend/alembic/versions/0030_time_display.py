"""add user time display preference

Revision ID: 0030_time_display
Revises: 0029_fix_heartbeat_participants
"""

import sqlalchemy as sa

from alembic import op

revision = "0030_time_display"
down_revision = "0029_fix_heartbeat_participants"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("app_config", sa.Column("time_display", sa.String(8), nullable=False, server_default="local"))


def downgrade() -> None:
    op.drop_column("app_config", "time_display")
