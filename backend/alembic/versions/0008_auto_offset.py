"""add automatic offset configuration

Revision ID: 0008_auto_offset
Revises: 0007_js8_api_messages
"""

import sqlalchemy as sa

from alembic import op

revision = "0008_auto_offset"
down_revision = "0007_js8_api_messages"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("app_config", sa.Column("offset_mode", sa.String(16), nullable=False, server_default="auto"))
    op.add_column("app_config", sa.Column("fixed_offset", sa.Integer(), nullable=False, server_default="1500"))


def downgrade() -> None:
    op.drop_column("app_config", "fixed_offset")
    op.drop_column("app_config", "offset_mode")
