"""add received message retention setting"""

import sqlalchemy as sa

from alembic import op

revision = "0014_received_message_retention"
down_revision = "0013_sender_source"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "app_config",
        sa.Column("received_message_retention_days", sa.Integer(), nullable=False, server_default="90"),
    )


def downgrade() -> None:
    op.drop_column("app_config", "received_message_retention_days")
