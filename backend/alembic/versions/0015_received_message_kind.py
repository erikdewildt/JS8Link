"""classify received traffic for message and monitor views"""

import sqlalchemy as sa

from alembic import op

revision = "0015_received_message_kind"
down_revision = "0014_received_message_retention"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("received_messages", sa.Column("kind", sa.String(24), nullable=True))


def downgrade() -> None:
    op.drop_column("received_messages", "kind")
