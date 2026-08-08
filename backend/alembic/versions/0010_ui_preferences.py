"""store user interface preferences

Revision ID: 0010_ui_preferences
Revises: 0009_map_history_preference
"""

import sqlalchemy as sa

from alembic import op

revision = "0010_ui_preferences"
down_revision = "0009_map_history_preference"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("app_config", sa.Column("language", sa.String(8), nullable=False, server_default="nl"))
    op.add_column("app_config", sa.Column("theme", sa.String(8), nullable=False, server_default="dark"))
    op.add_column("app_config", sa.Column("monitor_band", sa.String(16)))
    op.add_column(
        "app_config", sa.Column("monitor_sort_key", sa.String(32), nullable=False, server_default="received_at")
    )
    op.add_column(
        "app_config", sa.Column("monitor_sort_direction", sa.String(4), nullable=False, server_default="desc")
    )
    op.add_column("app_config", sa.Column("monitor_map_height", sa.Integer(), nullable=False, server_default="400"))


def downgrade() -> None:
    for column in (
        "monitor_map_height",
        "monitor_sort_direction",
        "monitor_sort_key",
        "monitor_band",
        "theme",
        "language",
    ):
        op.drop_column("app_config", column)
