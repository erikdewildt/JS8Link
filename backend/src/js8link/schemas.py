# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026  JS8Link contributors
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ConnectionRequest(BaseModel):
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(ge=1, le=65535)


class SetupRequest(ConnectionRequest):
    auth_enabled: bool = False
    username: str | None = None
    password: str | None = None


class ConfigPatch(BaseModel):
    host: str | None = None
    port: int | None = Field(default=None, ge=1, le=65535)
    auth_enabled: bool | None = None
    username: str | None = None
    password: str | None = None
    update_repository: str | None = Field(default=None, max_length=255)
    update_branch: str | None = Field(default=None, min_length=1, max_length=128)
    station_queries_enabled: bool | None = None
    query_interval_snr_minutes: int | None = Field(default=None, ge=15, le=1440)
    query_interval_hearing_minutes: int | None = Field(default=None, ge=15, le=1440)
    query_interval_info_days: int | None = Field(default=None, ge=1, le=365)
    query_interval_grid_days: int | None = Field(default=None, ge=1, le=365)
    query_interval_status_hours: int | None = Field(default=None, ge=1, le=168)
    query_max_per_hour: int | None = Field(default=None, ge=1, le=60)
    query_cooldown_seconds: int | None = Field(default=None, ge=60, le=3600)
    query_timeout_minutes: int | None = Field(default=None, ge=1, le=60)
    api_message_retention_days: int | None = Field(default=None, ge=1, le=365)
    diagnostics_enabled: bool | None = None
    diagnostics_retention_days: int | None = Field(default=None, ge=1, le=365)
    toast_duration_seconds: int | None = Field(default=None, ge=1, le=60)


class MessageRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5000)
    callsign: str | None = Field(default=None, max_length=32)
    delivery_mode: Literal["best_effort", "confirmed"] = "best_effort"


class StationContactPatch(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    qth: str | None = Field(default=None, max_length=128)
    notes: str | None = Field(default=None, max_length=5000)


class FrequencyRequest(BaseModel):
    dial: int = Field(ge=0)
    offset: int = Field(ge=1000, le=2500)


class SpeedRequest(BaseModel):
    speed: int = Field(ge=0)


class ChatSpeedPatch(BaseModel):
    speed: Literal[0, 1, 2, 4, 8]


class MapPreferencesPatch(BaseModel):
    history_minutes: int = Field(ge=15, le=1440)


class UIPreferencesPatch(BaseModel):
    language: Literal["nl", "en"] | None = None
    theme: Literal["dark", "light", "forest", "field-light", "high-contrast"] | None = None
    time_display: Literal["utc", "local"] | None = None
    monitor_band: str | None = Field(default=None, max_length=16)
    monitor_sort_key: Literal["sender", "received_at", "band", "type", "snr", "offset", "mode"] | None = None
    monitor_sort_direction: Literal["asc", "desc"] | None = None
    monitor_map_height: int | None = Field(default=None, ge=280, le=900)
    monitor_map_center_latitude: float | None = Field(default=None, ge=-90, le=90)
    monitor_map_center_longitude: float | None = Field(default=None, ge=-180, le=180)
    monitor_map_zoom: float | None = Field(default=None, ge=0, le=24)
    monitor_map_popups: bool | None = None
    monitor_map_greyline: bool | None = None
    monitor_map_bidirectional_only: bool | None = None
    monitor_map_cluster_stations: bool | None = None
    monitor_view: Literal["messages", "activity", "last_heard"] | None = None
    selected_chat_callsign: str | None = Field(default=None, max_length=32)
    history_minutes: int | None = Field(default=None, ge=15, le=1440)
    received_message_retention_days: int | None = Field(default=None, ge=1, le=3650)
    band_scope_minutes: int | None = Field(default=None, ge=1, le=1440)


class JS8SettingsPatch(BaseModel):
    grid: str | None = Field(default=None, max_length=8)
    info: str | None = Field(default=None, max_length=100)
    status: str | None = Field(default=None, max_length=100)
    dial: int | None = Field(default=None, ge=0)
    offset: int | None = Field(default=None, ge=1000, le=2500)
    offset_mode: Literal["auto", "fixed"] | None = None
    fixed_offset: int | None = Field(default=None, ge=1000, le=2500)
    speed: int | None = Field(default=None, ge=0)
    spot: bool | None = None


class EventEnvelope(BaseModel):
    event: str
    data: dict[str, Any]
    timestamp: datetime


class AutoreplyConfirmRequest(BaseModel):
    confirm_id: str
    accept: bool


class GroupsRequest(BaseModel):
    groups: list[str]


class HbIntervalRequest(BaseModel):
    interval: int = Field(ge=1, le=1440)  # minutes


class BoolToggleRequest(BaseModel):
    enabled: bool


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
class AuthRequest(BaseModel):
    password: str = Field(min_length=1, max_length=256)


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------
class HealthResponse(BaseModel):
    status: str
    connected: bool
    callsign: str | None
    version: str


class AboutResponse(BaseModel):
    application: str
    version: str
    channel: Literal["alpha", "beta", "rc", "stable"]
    license: str
    repository_url: str
    releases_url: str
    platform: str
    architecture: str
    js8call_protocol: Literal["tcp"]
    js8call_host: str
    js8call_port: int
    js8call_connected: bool
    update_state: str


class HelpSectionResponse(BaseModel):
    heading: str
    body: str


class HelpReferenceResponse(BaseModel):
    label: str
    href: str


class HelpTopicResponse(BaseModel):
    id: str
    title: str
    summary: str
    sections: list[HelpSectionResponse]
    steps: list[str]
    troubleshooting: list[str]
    references: list[HelpReferenceResponse]
    related: list[str]


class HelpCatalogResponse(BaseModel):
    language: Literal["nl", "en"]
    version: int
    topics: list[HelpTopicResponse]


class SetupStatusResponse(BaseModel):
    setup_complete: bool
    host: str
    port: int
    connected: bool
    auth_enabled: bool


class ConfigResponse(BaseModel):
    host: str
    port: int
    auth_enabled: bool
    setup_complete: bool
    offset_mode: str
    fixed_offset: int
    heartbeat_offset_mode: str
    fixed_heartbeat_offset: int
    received_message_retention_days: int
    api_message_retention_days: int
    diagnostics_enabled: bool
    diagnostics_retention_days: int
    update_repository: str | None
    update_branch: str
    station_queries_enabled: bool
    query_interval_snr_minutes: int
    query_interval_hearing_minutes: int
    query_interval_info_days: int
    query_interval_grid_days: int
    query_interval_status_hours: int
    query_max_per_hour: int
    query_cooldown_seconds: int
    query_timeout_minutes: int
    band_scope_minutes: int
    toast_duration_seconds: int


class StatusResponse(BaseModel):
    connected: bool
    callsign: str | None
    dial: int | None
    offset: int | None
    band: str | None
    speed: int | None
    mode_name: str | None
    grid: str | None
    info: str | None
    status_text: str | None
    version: str | None
    js8call_version: str | None
    offset_mode: str
    fixed_offset: int
    normal_offset: int
    tx_queue_depth: int | None
    rx_enabled: bool
    tx_enabled: bool
    os_name: str | None
    os_kernel: str | None
    os_kernel_version: str | None


class PreferencesResponse(BaseModel):
    language: str
    theme: str
    time_display: str
    monitor_band: str | None
    monitor_sort_key: str
    monitor_sort_direction: str
    monitor_map_height: int
    monitor_map_center_latitude: float
    monitor_map_center_longitude: float
    monitor_map_zoom: float
    monitor_map_popups: bool
    monitor_map_greyline: bool
    monitor_map_bidirectional_only: bool
    monitor_map_cluster_stations: bool
    toast_duration_seconds: int
    monitor_view: str
    selected_chat_callsign: str | None
    history_minutes: int
    received_message_retention_days: int
    band_scope_minutes: int


class SendMessageResponse(BaseModel):
    id: int
    status: str
    protocol_id: str | None
    delivery_mode: str
    delivery_status: str | None


class PTTResponse(BaseModel):
    ptt: bool
    message: str


class OSResponse(BaseModel):
    os_name: str | None
    os_kernel: str | None
    os_kernel_version: str | None


class CallActivityResponse(BaseModel):
    calls: dict[str, Any]


# ---------------------------------------------------------------------------
# Roadmap request models
# ---------------------------------------------------------------------------
class SpotRequest(BaseModel):
    enabled: bool


class TxTextRequest(BaseModel):
    text: str = Field(max_length=5000)


class InboxStoreRequest(BaseModel):
    callsign: str = Field(max_length=32)
    text: str = Field(max_length=5000)


class FilterPatch(BaseModel):
    center: int | None = Field(default=None, ge=500, le=2500)
    width: int | None = Field(default=None, ge=50, le=500)


class FilterEnabledRequest(BaseModel):
    enabled: bool


class TuneRequest(BaseModel):
    enabled: bool


class CallSelectedResponse(BaseModel):
    callsign: str | None


class CallSelectedRequest(BaseModel):
    callsign: str = Field(min_length=1, max_length=32)


class TxTextResponse(BaseModel):
    text: str


class FilterResponse(BaseModel):
    center: int | None
    width: int | None
    enabled: bool | None


class BandActivityResponse(BaseModel):
    offsets: list[dict[str, Any]]
    total_active: int
    timestamp: datetime


class TxQueueResponse(BaseModel):
    active: bool
    current_message: str | None
    frames_sent: int
    estimated_frames: int
    progress_pct: int
    queue_depth: int
    queued_messages: list[dict[str, Any]]
    timestamp: datetime


class GenericStatusResponse(BaseModel):
    status: str


class PurgeResponse(BaseModel):
    status: str
    deleted: dict[str, int]


class DiagnosticProcessingResponse(BaseModel):
    id: int
    sequence: int
    operation: str
    outcome: str
    detail: str
    payload: str | None
    created_at: datetime | None


class DiagnosticTraceSummaryResponse(BaseModel):
    trace_id: str
    source: str
    event_type: str
    severity: str
    summary: str
    interpretation: str
    created_at: datetime | None


class DiagnosticTraceDetailResponse(DiagnosticTraceSummaryResponse):
    raw_payload: str | None
    processing: list[DiagnosticProcessingResponse]


class DiagnosticTraceListResponse(BaseModel):
    traces: list[DiagnosticTraceSummaryResponse]


# ---------------------------------------------------------------------------
# Station query models
# ---------------------------------------------------------------------------
class StationQueryRequest(BaseModel):
    query_type: Literal["snr", "hearing", "info", "grid", "status"]


class StationQueryResponse(BaseModel):
    id: int
    station_id: int
    query_type: str
    requested_at: datetime
    responded_at: datetime | None
    response_text: str | None
    status: str
    snr_value: int | None
    hearing_data: str | None
    error_message: str | None


class StationDetailResponse(BaseModel):
    callsign: str
    name: str | None
    qth: str | None
    notes: str | None
    grid: str | None
    latitude: float | None
    longitude: float | None
    country: str | None
    location_source: str | None
    grid_source: str | None
    first_seen: datetime | None
    last_seen: datetime | None
    last_snr: int | None
    last_offset: int | None
    last_mode: str | None
    message_count: int
    js8link_version: int | None
    js8link_last_seen: datetime | None
    # Query results
    info_text: str | None
    info_updated_at: datetime | None
    status_text: str | None
    status_updated_at: datetime | None
    hearing_report: list[dict[str, Any]] | None
    hearing_updated_at: datetime | None
    # Query timestamps
    last_snr_query_at: datetime | None
    last_hearing_query_at: datetime | None
    last_info_query_at: datetime | None
    last_grid_query_at: datetime | None
    last_status_query_at: datetime | None
