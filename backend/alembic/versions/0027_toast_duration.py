"""add received message toast duration

Revision ID: 0027_toast_duration
Revises: 0026_api_message_retention
"""

import sqlalchemy as sa

from alembic import op

revision = "0027_toast_duration"
down_revision = "0026_api_message_retention"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "app_config",
        sa.Column("toast_duration_seconds", sa.Integer(), nullable=False, server_default="5"),
    )


def downgrade() -> None:
    op.drop_column("app_config", "toast_duration_seconds")
