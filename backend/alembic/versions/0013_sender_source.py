"""track whether received senders are explicit or inferred"""

import sqlalchemy as sa

from alembic import op

revision = "0013_sender_source"
down_revision = "0012_js8call_v3_features"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("received_messages", sa.Column("sender_source", sa.String(24), nullable=True))


def downgrade() -> None:
    op.drop_column("received_messages", "sender_source")
