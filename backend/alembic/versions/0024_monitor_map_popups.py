"""add monitor map popup preference

Revision ID: 0024_monitor_map_popups
Revises: 0023_chat_archived
"""

import sqlalchemy as sa

from alembic import op

revision = "0024_monitor_map_popups"
down_revision = "0023_chat_archived"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "app_config",
        sa.Column("monitor_map_popups", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column("app_config", "monitor_map_popups")
