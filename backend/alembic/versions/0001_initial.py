"""initial schema

Revision ID: 0001_initial
Revises:
"""

import sqlalchemy as sa

from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("js8_host", sa.String(255), nullable=False),
        sa.Column("js8_port", sa.Integer(), nullable=False),
        sa.Column("setup_complete", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_table(
        "auth_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("username", sa.String(255)),
        sa.Column("password_hash", sa.String(512)),
    )
    op.create_table(
        "received_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("callsign", sa.String(32)),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("message_type", sa.String(64), nullable=False),
        sa.Column("grid", sa.String(16)),
        sa.Column("frequency", sa.Integer()),
        sa.Column("offset", sa.Integer()),
        sa.Column("snr", sa.Integer()),
        sa.Column("received_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_table(
        "transmitted_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("callsign", sa.String(32)),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("transmitted_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_table(
        "activity_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_type", sa.String(128), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.execute("INSERT INTO app_config (id, js8_host, js8_port, setup_complete) VALUES (1, '127.0.0.1', 2442, 0)")
    op.execute("INSERT INTO auth_config (id, enabled) VALUES (1, 0)")


def downgrade() -> None:
    for table in ("activity_events", "transmitted_messages", "received_messages", "auth_config", "app_config"):
        op.drop_table(table)
