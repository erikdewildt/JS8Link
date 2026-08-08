"""use 2442 for new JS8Call connections

Revision ID: 0002_default_api_port
Revises: 0001_initial
"""

from alembic import op

revision = "0002_default_api_port"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE app_config SET js8_port = 2442 WHERE setup_complete = 0 AND js8_port = 2242")


def downgrade() -> None:
    op.execute("UPDATE app_config SET js8_port = 2242 WHERE setup_complete = 0 AND js8_port = 2442")
