"""add protocol version to transmitted messages

Revision ID: 0022_transmitted_protocol_version
Revises: 0021_update_settings
"""

import sqlalchemy as sa

from alembic import op

revision = "0022_transmitted_protocol_version"
down_revision = "0021_update_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "transmitted_messages",
        sa.Column("protocol_version", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("transmitted_messages", "protocol_version")
