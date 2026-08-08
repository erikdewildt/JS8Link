"""add application update settings

Revision ID: 0021_update_settings
Revises: 0020_arq_delivery
"""

import sqlalchemy as sa

from alembic import op

revision = "0021_update_settings"
down_revision = "0020_arq_delivery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("app_config", sa.Column("update_repository", sa.String(255), nullable=True))
    op.add_column(
        "app_config",
        sa.Column("update_branch", sa.String(128), server_default="main", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("app_config", "update_branch")
    op.drop_column("app_config", "update_repository")
