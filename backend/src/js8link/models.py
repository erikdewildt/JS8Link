# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026  JS8Link contributors
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class AppConfig(Base):
    __tablename__ = "app_config"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    js8_host: Mapped[str] = mapped_column(String(255), default="127.0.0.1")
    js8_port: Mapped[int] = mapped_column(Integer, default=2442)
    offset_mode: Mapped[str] = mapped_column(String(16), default="auto")
    fixed_offset: Mapped[int] = mapped_column(Integer, default=1500)
    map_history_minutes: Mapped[int] = mapped_column(Integer, default=1440)
    language: Mapped[str] = mapped_column(String(8), default="nl")
    theme: Mapped[str] = mapped_column(String(8), default="dark")
    time_display: Mapped[str] = mapped_column(String(8), default="local")
    monitor_band: Mapped[str | None] = mapped_column(String(16), nullable=True)
    monitor_sort_key: Mapped[str] = mapped_column(String(32), default="received_at")
    monitor_sort_direction: Mapped[str] = mapped_column(String(4), default="desc")
    monitor_map_height: Mapped[int] = mapped_column(Integer, default=400)
    monitor_map_center_latitude: Mapped[float] = mapped_column(Float, default=52.0)
    monitor_map_center_longitude: Mapped[float] = mapped_column(Float, default=5.0)
    monitor_map_zoom: Mapped[float] = mapped_column(Float, default=3.0)
    monitor_map_popups: Mapped[bool] = mapped_column(Boolean, default=True)
    monitor_map_greyline: Mapped[bool] = mapped_column(Boolean, default=True)
    monitor_map_bidirectional_only: Mapped[bool] = mapped_column(Boolean, default=False)
    monitor_map_cluster_stations: Mapped[bool] = mapped_column(Boolean, default=True)
    toast_duration_seconds: Mapped[int] = mapped_column(Integer, default=5)
    monitor_view: Mapped[str] = mapped_column(String(16), default="messages")
    selected_chat_callsign: Mapped[str | None] = mapped_column(String(32), nullable=True)
    received_message_retention_days: Mapped[int] = mapped_column(Integer, default=90)
    api_message_retention_days: Mapped[int] = mapped_column(Integer, default=7)
    diagnostics_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    diagnostics_retention_days: Mapped[int] = mapped_column(Integer, default=7)
    setup_complete: Mapped[bool] = mapped_column(Boolean, default=False)
    js8call_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    heartbeat_offset_mode: Mapped[str] = mapped_column(String(16), default="auto")
    fixed_heartbeat_offset: Mapped[int] = mapped_column(Integer, default=800)
    update_repository: Mapped[str | None] = mapped_column(String(255), nullable=True)
    update_branch: Mapped[str] = mapped_column(String(128), default="main")
    # Station query intervals
    query_interval_snr_minutes: Mapped[int] = mapped_column(Integer, default=60)
    station_queries_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    query_interval_hearing_minutes: Mapped[int] = mapped_column(Integer, default=60)
    query_interval_info_days: Mapped[int] = mapped_column(Integer, default=14)
    query_interval_grid_days: Mapped[int] = mapped_column(Integer, default=14)
    query_interval_status_hours: Mapped[int] = mapped_column(Integer, default=24)
    query_max_per_hour: Mapped[int] = mapped_column(Integer, default=12)
    query_cooldown_seconds: Mapped[int] = mapped_column(Integer, default=120)
    query_timeout_minutes: Mapped[int] = mapped_column(Integer, default=5)
    band_scope_minutes: Mapped[int] = mapped_column(Integer, default=15)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class AuthConfig(Base):
    __tablename__ = "auth_config"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(512), nullable=True)


class ChatReadState(Base):
    __tablename__ = "chat_read_state"
    callsign: Mapped[str] = mapped_column(String(32), primary_key=True)
    last_read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    preferred_speed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class ReceivedMessage(Base):
    __tablename__ = "received_messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    callsign: Mapped[str | None] = mapped_column(String(32))
    sender_source: Mapped[str | None] = mapped_column(String(24), nullable=True)
    kind: Mapped[str | None] = mapped_column(String(24), nullable=True)
    delivery_mode: Mapped[str] = mapped_column(
        String(24), default="best_effort", server_default="best_effort", nullable=False
    )
    protocol_id: Mapped[str | None] = mapped_column(String(16), nullable=True)
    text: Mapped[str] = mapped_column(Text)
    message_type: Mapped[str] = mapped_column(String(64), default="rx")
    grid: Mapped[str | None] = mapped_column(String(16))
    frequency: Mapped[int | None] = mapped_column(Integer)
    offset: Mapped[int | None] = mapped_column(Integer)
    band: Mapped[str | None] = mapped_column(String(16))
    mode: Mapped[str | None] = mapped_column(String(32))
    snr: Mapped[int | None] = mapped_column(Integer)
    tdrift: Mapped[float | None] = mapped_column(Float, nullable=True)
    from_callsign: Mapped[str | None] = mapped_column(String(32))
    to_callsign: Mapped[str | None] = mapped_column(String(32))
    command: Mapped[str | None] = mapped_column(String(64))
    is_heartbeat: Mapped[bool] = mapped_column(Boolean, default=False)
    utc_timestamp: Mapped[datetime | None] = mapped_column(DateTime)
    raw_payload: Mapped[str | None] = mapped_column(Text)
    received_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Station(Base):
    __tablename__ = "stations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    callsign: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    qth: Mapped[str | None] = mapped_column(String(128), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    js8link_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    js8link_last_seen: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    grid: Mapped[str | None] = mapped_column(String(16))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    country: Mapped[str | None] = mapped_column(String(128))
    location_source: Mapped[str | None] = mapped_column(String(32))
    first_seen: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_seen: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_snr: Mapped[int | None] = mapped_column(Integer)
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    last_offset: Mapped[int | None] = mapped_column(Integer)
    last_mode: Mapped[str | None] = mapped_column(String(32))
    last_tdrift: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Query timestamps
    last_snr_query_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_hearing_query_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_info_query_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_grid_query_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_status_query_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Query results
    hearing_report: Mapped[str | None] = mapped_column(Text, nullable=True)
    hearing_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    info_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    info_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    status_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    grid_source: Mapped[str | None] = mapped_column(String(16), nullable=True)


class StationQuery(Base):
    __tablename__ = "station_queries"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    station_id: Mapped[int] = mapped_column(ForeignKey("stations.id"), index=True)
    query_type: Mapped[str] = mapped_column(String(16))  # snr/hearing/info/grid/status
    requested_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    responded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    response_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending/responded/timeout/failed
    snr_value: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hearing_data: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class StationLink(Base):
    __tablename__ = "station_links"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_station_id: Mapped[int] = mapped_column(ForeignKey("stations.id"))
    target_station_id: Mapped[int] = mapped_column(ForeignKey("stations.id"))
    relation_type: Mapped[str] = mapped_column(String(32), default="heartbeat")
    band: Mapped[str | None] = mapped_column(String(16))
    latest_snr: Mapped[int | None] = mapped_column(Integer)
    average_snr: Mapped[float | None] = mapped_column(Float)
    best_snr: Mapped[int | None] = mapped_column(Integer)
    observation_count: Mapped[int] = mapped_column(Integer, default=0)
    first_seen: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_seen: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class TransmittedMessage(Base):
    __tablename__ = "transmitted_messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    callsign: Mapped[str | None] = mapped_column(String(32))
    text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="queued")
    delivery_mode: Mapped[str] = mapped_column(String(24), default="best_effort")
    protocol_id: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    protocol_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    delivery_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=1)
    max_attempts: Mapped[int] = mapped_column(Integer, default=1)
    ack_deadline: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    tx_frame_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    band: Mapped[str | None] = mapped_column(String(16), nullable=True)
    offset: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    transmitted_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ArqReceipt(Base):
    __tablename__ = "arq_receipts"
    __table_args__ = (
        UniqueConstraint("callsign", "protocol_version", "protocol_id", name="uq_arq_receipt_sender_message"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    callsign: Mapped[str] = mapped_column(String(32), index=True)
    protocol_version: Mapped[int] = mapped_column(Integer)
    protocol_id: Mapped[str] = mapped_column(String(16))
    received_message_id: Mapped[int | None] = mapped_column(ForeignKey("received_messages.id"), nullable=True)
    first_received_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_received_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0)
    ack_sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ActivityEvent(Base):
    __tablename__ = "activity_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_type: Mapped[str] = mapped_column(String(128))
    payload: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class JS8APIMessage(Base):
    __tablename__ = "js8_api_messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    direction: Mapped[str] = mapped_column(String(16))
    message_type: Mapped[str] = mapped_column(String(128), index=True)
    request_id: Mapped[int | None] = mapped_column(Integer, index=True)
    params_json: Mapped[str] = mapped_column(Text)
    value_json: Mapped[str] = mapped_column(Text)
    utc_timestamp: Mapped[datetime | None] = mapped_column(DateTime)
    received_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    raw_payload: Mapped[str] = mapped_column(Text)


class DiagnosticTrace(Base):
    """One observable action, retaining its input and human interpretation."""

    __tablename__ = "diagnostic_traces"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trace_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    source: Mapped[str] = mapped_column(String(32), index=True)
    event_type: Mapped[str] = mapped_column(String(128), index=True)
    severity: Mapped[str] = mapped_column(String(16), default="info", index=True)
    summary: Mapped[str] = mapped_column(Text)
    raw_payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    interpretation: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)


class DiagnosticProcessing(Base):
    """A concrete processing step belonging to a diagnostic trace."""

    __tablename__ = "diagnostic_processing"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trace_id: Mapped[str] = mapped_column(ForeignKey("diagnostic_traces.trace_id"), index=True)
    sequence: Mapped[int] = mapped_column(Integer, default=1)
    operation: Mapped[str] = mapped_column(String(128))
    outcome: Mapped[str] = mapped_column(String(16), default="ok")
    detail: Mapped[str] = mapped_column(Text)
    payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
