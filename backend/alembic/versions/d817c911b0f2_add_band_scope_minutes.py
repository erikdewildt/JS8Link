"""add band scope minutes

Revision ID: d817c911b0f2
Revises: 0e83a15a0d81
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d817c911b0f2"
down_revision: str | None = "0e83a15a0d81"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "app_config",
        sa.Column("band_scope_minutes", sa.Integer(), nullable=False, server_default="15"),
    )


def downgrade() -> None:
    op.drop_column("app_config", "band_scope_minutes")
