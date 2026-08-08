"""store received message band

Revision ID: 0005_received_message_band
Revises: 0004_station_location_source
"""

import sqlalchemy as sa

from alembic import op

revision = "0005_received_message_band"
down_revision = "0004_station_location_source"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("received_messages", sa.Column("band", sa.String(16)))


def downgrade() -> None:
    op.drop_column("received_messages", "band")
