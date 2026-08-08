"""add editable station contact information

Revision ID: 0019_station_contact
Revises: 0018_chat_read_state
"""

import sqlalchemy as sa

from alembic import op

revision = "0019_station_contact"
down_revision = "0018_chat_read_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("stations", sa.Column("name", sa.String(128), nullable=True))
    op.add_column("stations", sa.Column("qth", sa.String(128), nullable=True))
    op.add_column("stations", sa.Column("notes", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("stations", "notes")
    op.drop_column("stations", "qth")
    op.drop_column("stations", "name")
