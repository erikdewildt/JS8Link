"""add JS8Link ARQ delivery tracking

Revision ID: 0020_arq_delivery
Revises: 0019_station_contact
"""

import sqlalchemy as sa

from alembic import op

revision = "0020_arq_delivery"
down_revision = "0019_station_contact"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "received_messages",
        sa.Column("delivery_mode", sa.String(24), server_default="best_effort", nullable=False),
    )
    op.add_column("received_messages", sa.Column("protocol_id", sa.String(16), nullable=True))
    op.add_column("stations", sa.Column("js8link_version", sa.Integer(), nullable=True))
    op.add_column("stations", sa.Column("js8link_last_seen", sa.DateTime(), nullable=True))
    op.add_column(
        "transmitted_messages",
        sa.Column("delivery_mode", sa.String(24), server_default="best_effort", nullable=False),
    )
    op.add_column("transmitted_messages", sa.Column("protocol_id", sa.String(16), nullable=True))
    op.add_column("transmitted_messages", sa.Column("delivery_status", sa.String(32), nullable=True))
    op.add_column("transmitted_messages", sa.Column("attempts", sa.Integer(), server_default="1", nullable=False))
    op.add_column("transmitted_messages", sa.Column("max_attempts", sa.Integer(), server_default="1", nullable=False))
    op.add_column("transmitted_messages", sa.Column("ack_deadline", sa.DateTime(), nullable=True))
    op.add_column("transmitted_messages", sa.Column("delivered_at", sa.DateTime(), nullable=True))
    op.add_column("transmitted_messages", sa.Column("last_error", sa.Text(), nullable=True))
    op.create_index("ix_transmitted_messages_protocol_id", "transmitted_messages", ["protocol_id"])
    op.create_table(
        "arq_receipts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("callsign", sa.String(32), nullable=False),
        sa.Column("protocol_version", sa.Integer(), nullable=False),
        sa.Column("protocol_id", sa.String(16), nullable=False),
        sa.Column("received_message_id", sa.Integer(), sa.ForeignKey("received_messages.id"), nullable=True),
        sa.Column("first_received_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("last_received_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("duplicate_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("ack_sent_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("callsign", "protocol_version", "protocol_id", name="uq_arq_receipt_sender_message"),
    )
    op.create_index("ix_arq_receipts_callsign", "arq_receipts", ["callsign"])


def downgrade() -> None:
    op.drop_index("ix_arq_receipts_callsign", table_name="arq_receipts")
    op.drop_table("arq_receipts")
    op.drop_index("ix_transmitted_messages_protocol_id", table_name="transmitted_messages")
    for column in (
        "last_error",
        "delivered_at",
        "ack_deadline",
        "max_attempts",
        "attempts",
        "delivery_status",
        "protocol_id",
        "delivery_mode",
    ):
        op.drop_column("transmitted_messages", column)
    op.drop_column("stations", "js8link_last_seen")
    op.drop_column("stations", "js8link_version")
    op.drop_column("received_messages", "protocol_id")
    op.drop_column("received_messages", "delivery_mode")
