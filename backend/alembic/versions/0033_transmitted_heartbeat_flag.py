"""mark locally transmitted heartbeat frames

Revision ID: 0033_transmitted_heartbeat_flag
Revises: 59d120930007
"""

import sqlalchemy as sa

from alembic import op

revision = "0033_transmitted_heartbeat_flag"
down_revision = "59d120930007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "transmitted_messages",
        sa.Column("is_heartbeat", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    )
    # Older local TX rows did not carry a classification.  Heartbeat frames
    # are protocol traffic and can be identified safely from their persisted
    # display text for the chat-history migration.
    op.execute(
        sa.text(
            "UPDATE transmitted_messages "
            "SET is_heartbeat = 1 "
            "WHERE UPPER(text) LIKE '%HEARTBEAT%'"
        )
    )


def downgrade() -> None:
    op.drop_column("transmitted_messages", "is_heartbeat")
