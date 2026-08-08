"""store station link band

Revision ID: 0006_station_link_band
Revises: 0005_received_message_band
"""

import sqlalchemy as sa

from alembic import op

revision = "0006_station_link_band"
down_revision = "0005_received_message_band"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("station_links", sa.Column("band", sa.String(16)))


def downgrade() -> None:
    op.drop_column("station_links", "band")
