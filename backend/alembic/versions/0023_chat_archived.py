"""add archived state to chat read state

Revision ID: 0023_chat_archived
Revises: d817c911b0f2
"""

import sqlalchemy as sa

from alembic import op

revision = "0023_chat_archived"
down_revision = "d817c911b0f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "chat_read_state",
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("chat_read_state", "archived")
