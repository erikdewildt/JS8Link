"""add chat read state and selected chat preference

Revision ID: 0018_chat_read_state
Revises: 0017_monitor_map_viewport
"""

import sqlalchemy as sa

from alembic import op

revision = "0018_chat_read_state"
down_revision = "0017_monitor_map_viewport"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("app_config", sa.Column("selected_chat_callsign", sa.String(32), nullable=True))
    op.create_table(
        "chat_read_state",
        sa.Column("callsign", sa.String(32), primary_key=True),
        sa.Column("last_read_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("chat_read_state")
    op.drop_column("app_config", "selected_chat_callsign")
