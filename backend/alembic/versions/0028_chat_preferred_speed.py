"""store a preferred speed for each chat

Revision ID: 0028_chat_preferred_speed
Revises: 0027_toast_duration
"""

import sqlalchemy as sa

from alembic import op

revision = "0028_chat_preferred_speed"
down_revision = "0027_toast_duration"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "chat_read_state",
        sa.Column("preferred_speed", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("chat_read_state", "preferred_speed")
