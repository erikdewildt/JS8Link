"""add monitor stations and heartbeat relationships

Revision ID: 0003_monitor
Revises: 0002_default_api_port
"""

import sqlalchemy as sa

from alembic import op

revision = "0003_monitor"
down_revision = "0002_default_api_port"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("received_messages", sa.Column("from_callsign", sa.String(32)))
    op.add_column("received_messages", sa.Column("to_callsign", sa.String(32)))
    op.add_column("received_messages", sa.Column("command", sa.String(64)))
    op.add_column(
        "received_messages", sa.Column("is_heartbeat", sa.Boolean(), nullable=False, server_default=sa.false())
    )
    op.add_column("received_messages", sa.Column("utc_timestamp", sa.DateTime()))
    op.add_column("received_messages", sa.Column("raw_payload", sa.Text()))
    op.create_index("ix_received_messages_received_at", "received_messages", ["received_at"])
    op.create_index("ix_received_messages_callsign", "received_messages", ["callsign"])
    op.create_table(
        "stations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("callsign", sa.String(32), nullable=False, unique=True),
        sa.Column("grid", sa.String(16)),
        sa.Column("latitude", sa.Float()),
        sa.Column("longitude", sa.Float()),
        sa.Column("first_seen", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("last_snr", sa.Integer()),
        sa.Column("message_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_table(
        "station_links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_station_id", sa.Integer(), sa.ForeignKey("stations.id"), nullable=False),
        sa.Column("target_station_id", sa.Integer(), sa.ForeignKey("stations.id"), nullable=False),
        sa.Column("relation_type", sa.String(32), nullable=False),
        sa.Column("latest_snr", sa.Integer()),
        sa.Column("average_snr", sa.Float()),
        sa.Column("best_snr", sa.Integer()),
        sa.Column("observation_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("first_seen", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("source_station_id", "target_station_id", "relation_type"),
    )


def downgrade() -> None:
    op.drop_table("station_links")
    op.drop_table("stations")
    for name in ("raw_payload", "utc_timestamp", "is_heartbeat", "command", "to_callsign", "from_callsign"):
        op.drop_column("received_messages", name)
    op.drop_index("ix_received_messages_callsign", table_name="received_messages")
    op.drop_index("ix_received_messages_received_at", table_name="received_messages")
