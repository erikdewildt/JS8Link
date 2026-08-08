"""store station fallback location metadata

Revision ID: 0004_station_location_source
Revises: 0003_monitor
"""

import sqlalchemy as sa

from alembic import op

revision = "0004_station_location_source"
down_revision = "0003_monitor"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("stations", sa.Column("country", sa.String(128)))
    op.add_column("stations", sa.Column("location_source", sa.String(32)))


def downgrade() -> None:
    op.drop_column("stations", "location_source")
    op.drop_column("stations", "country")
