"""store every received JS8Call API message

Revision ID: 0007_js8_api_messages
Revises: 0006_station_link_band
"""

import sqlalchemy as sa

from alembic import op

revision = "0007_js8_api_messages"
down_revision = "0006_station_link_band"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "js8_api_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("direction", sa.String(16), nullable=False),
        sa.Column("message_type", sa.String(128), nullable=False),
        sa.Column("request_id", sa.BigInteger()),
        sa.Column("params_json", sa.Text(), nullable=False),
        sa.Column("value_json", sa.Text(), nullable=False),
        sa.Column("utc_timestamp", sa.DateTime()),
        sa.Column("received_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("raw_payload", sa.Text(), nullable=False),
    )
    op.create_index("ix_js8_api_messages_received_at", "js8_api_messages", ["received_at"])
    op.create_index("ix_js8_api_messages_message_type", "js8_api_messages", ["message_type"])
    op.create_index("ix_js8_api_messages_request_id", "js8_api_messages", ["request_id"])


def downgrade() -> None:
    op.drop_index("ix_js8_api_messages_request_id", table_name="js8_api_messages")
    op.drop_index("ix_js8_api_messages_message_type", table_name="js8_api_messages")
    op.drop_index("ix_js8_api_messages_received_at", table_name="js8_api_messages")
    op.drop_table("js8_api_messages")
