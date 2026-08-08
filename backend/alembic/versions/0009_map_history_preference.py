"""store map history preference

Revision ID: 0009_map_history_preference
Revises: 0008_auto_offset
"""

import sqlalchemy as sa

from alembic import op

revision = "0009_map_history_preference"
down_revision = "0008_auto_offset"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("app_config", sa.Column("map_history_minutes", sa.Integer(), nullable=False, server_default="1440"))


def downgrade() -> None:
    op.drop_column("app_config", "map_history_minutes")
