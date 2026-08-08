"""add station query support

Revision ID: 0e83a15a0d81
Revises: 0022_transmitted_protocol_version
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '0e83a15a0d81'
down_revision: str | None = '0022_transmitted_protocol_version'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Station query log table
    op.create_table('station_queries',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('station_id', sa.Integer(), nullable=False),
    sa.Column('query_type', sa.String(length=16), nullable=False),
    sa.Column('requested_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('responded_at', sa.DateTime(), nullable=True),
    sa.Column('response_text', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('snr_value', sa.Integer(), nullable=True),
    sa.Column('hearing_data', sa.Text(), nullable=True),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['station_id'], ['stations.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_station_queries_station_id'), 'station_queries', ['station_id'], unique=False)
    # AppConfig query interval columns
    op.add_column(
        'app_config',
        sa.Column('query_interval_snr_minutes', sa.Integer(), nullable=False, server_default='60'),
    )
    op.add_column(
        'app_config',
        sa.Column('query_interval_hearing_minutes', sa.Integer(), nullable=False, server_default='60'),
    )
    op.add_column(
        'app_config',
        sa.Column('query_interval_info_days', sa.Integer(), nullable=False, server_default='14'),
    )
    op.add_column(
        'app_config',
        sa.Column('query_interval_grid_days', sa.Integer(), nullable=False, server_default='14'),
    )
    op.add_column(
        'app_config',
        sa.Column('query_interval_status_hours', sa.Integer(), nullable=False, server_default='24'),
    )
    op.add_column(
        'app_config',
        sa.Column('query_max_per_hour', sa.Integer(), nullable=False, server_default='12'),
    )
    op.add_column(
        'app_config',
        sa.Column('query_cooldown_seconds', sa.Integer(), nullable=False, server_default='120'),
    )
    op.add_column(
        'app_config',
        sa.Column('query_timeout_minutes', sa.Integer(), nullable=False, server_default='5'),
    )
    # Station query timestamp and result columns
    op.add_column('stations', sa.Column('last_snr_query_at', sa.DateTime(), nullable=True))
    op.add_column('stations', sa.Column('last_hearing_query_at', sa.DateTime(), nullable=True))
    op.add_column('stations', sa.Column('last_info_query_at', sa.DateTime(), nullable=True))
    op.add_column('stations', sa.Column('last_grid_query_at', sa.DateTime(), nullable=True))
    op.add_column('stations', sa.Column('last_status_query_at', sa.DateTime(), nullable=True))
    op.add_column('stations', sa.Column('hearing_report', sa.Text(), nullable=True))
    op.add_column('stations', sa.Column('hearing_updated_at', sa.DateTime(), nullable=True))
    op.add_column('stations', sa.Column('info_text', sa.Text(), nullable=True))
    op.add_column('stations', sa.Column('info_updated_at', sa.DateTime(), nullable=True))
    op.add_column('stations', sa.Column('status_text', sa.Text(), nullable=True))
    op.add_column('stations', sa.Column('status_updated_at', sa.DateTime(), nullable=True))
    op.add_column('stations', sa.Column('grid_source', sa.String(length=16), nullable=True))


def downgrade() -> None:
    op.drop_column('stations', 'grid_source')
    op.drop_column('stations', 'status_updated_at')
    op.drop_column('stations', 'status_text')
    op.drop_column('stations', 'info_updated_at')
    op.drop_column('stations', 'info_text')
    op.drop_column('stations', 'hearing_updated_at')
    op.drop_column('stations', 'hearing_report')
    op.drop_column('stations', 'last_status_query_at')
    op.drop_column('stations', 'last_grid_query_at')
    op.drop_column('stations', 'last_info_query_at')
    op.drop_column('stations', 'last_hearing_query_at')
    op.drop_column('stations', 'last_snr_query_at')
    op.drop_column('app_config', 'query_timeout_minutes')
    op.drop_column('app_config', 'query_cooldown_seconds')
    op.drop_column('app_config', 'query_max_per_hour')
    op.drop_column('app_config', 'query_interval_status_hours')
    op.drop_column('app_config', 'query_interval_grid_days')
    op.drop_column('app_config', 'query_interval_info_days')
    op.drop_column('app_config', 'query_interval_hearing_minutes')
    op.drop_column('app_config', 'query_interval_snr_minutes')
    op.drop_index(op.f('ix_station_queries_station_id'), table_name='station_queries')
    op.drop_table('station_queries')
