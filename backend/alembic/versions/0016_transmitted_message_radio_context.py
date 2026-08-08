"""store radio context for transmitted messages"""

import sqlalchemy as sa

from alembic import op

revision = "0016_transmitted_message_radio_context"
down_revision = "0015_received_message_kind"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("transmitted_messages", sa.Column("band", sa.String(16), nullable=True))
    op.add_column("transmitted_messages", sa.Column("offset", sa.Integer(), nullable=True))
    op.add_column("transmitted_messages", sa.Column("mode", sa.String(32), nullable=True))


def downgrade() -> None:
    op.drop_column("transmitted_messages", "mode")
    op.drop_column("transmitted_messages", "offset")
    op.drop_column("transmitted_messages", "band")
