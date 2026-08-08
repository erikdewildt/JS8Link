"""correct sender and recipient in stored heartbeat reports

Revision ID: 0029_fix_heartbeat_participants
Revises: 0028_chat_preferred_speed
"""

import re

import sqlalchemy as sa

from alembic import op

revision = "0029_fix_heartbeat_participants"
down_revision = "0028_chat_preferred_speed"
branch_labels = None
depends_on = None

_HEARTBEAT_REPORT = re.compile(
    r"^\s*([A-Z0-9/]{3,16})\s+([A-Z0-9/]{3,16})\s+HEARTBEAT\b",
    re.IGNORECASE,
)


def upgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(sa.text("SELECT id, text FROM received_messages WHERE is_heartbeat = 1"))
    for message_id, text in rows:
        match = _HEARTBEAT_REPORT.match(str(text or ""))
        if not match:
            continue
        sender, recipient = (value.upper() for value in match.groups())
        connection.execute(
            sa.text(
                """UPDATE received_messages
                   SET callsign = :sender,
                       from_callsign = :sender,
                       to_callsign = :recipient
                 WHERE id = :message_id"""
            ),
            {"sender": sender, "recipient": recipient, "message_id": message_id},
        )


def downgrade() -> None:
    # The previous participant assignment cannot be reconstructed safely.
    pass
