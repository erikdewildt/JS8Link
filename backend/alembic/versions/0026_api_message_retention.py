"""add API message retention setting

Revision ID: 0026_api_message_retention
Revises: 0025_station_queries_enabled
"""

import sqlalchemy as sa

from alembic import op

revision = "0026_api_message_retention"
down_revision = "0025_station_queries_enabled"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "app_config",
        sa.Column("api_message_retention_days", sa.Integer(), nullable=False, server_default="7"),
    )


def downgrade() -> None:
    op.drop_column("app_config", "api_message_retention_days")
