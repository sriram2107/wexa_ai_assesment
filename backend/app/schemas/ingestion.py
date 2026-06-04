"""
Pydantic v2 schemas for event ingestion, data sources, and API keys.
"""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ── Events ──────────────────────────────────────────────────────────

class EventCreate(BaseModel):
    event_name: str = Field(min_length=1, max_length=255)
    timestamp: Optional[datetime] = None
    properties: dict[str, Any] = Field(default_factory=dict)
    user_id: Optional[str] = None  # external user id
    session_id: Optional[str] = None
    numeric_value: Optional[float] = None


class BatchEventsCreate(BaseModel):
    events: list[EventCreate] = Field(min_length=1, max_length=1000)


class EventResponse(BaseModel):
    id: str
    event_name: str
    timestamp: datetime
    properties: dict[str, Any]
    user_id_ext: Optional[str] = None
    numeric_value: Optional[float] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class EventsListResponse(BaseModel):
    events: list[EventResponse]
    total: int
    page: int
    page_size: int


# ── Data Sources ────────────────────────────────────────────────────

class DataSourceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    source_type: str = Field(pattern="^(api|csv|webhook)$")
    config: dict[str, Any] = Field(default_factory=dict)


class DataSourceResponse(BaseModel):
    id: str
    name: str
    source_type: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ── API Keys ────────────────────────────────────────────────────────

class APIKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class APIKeyCreatedResponse(BaseModel):
    """Returned only at creation time — contains the full key."""
    id: str
    name: str
    key: str  # full key — only shown once
    key_prefix: str
    created_at: datetime


class APIKeyResponse(BaseModel):
    id: str
    name: str
    key_prefix: str
    is_active: bool
    last_used_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Ingestion Stats ────────────────────────────────────────────────

class IngestionStatsResponse(BaseModel):
    total_events: int
    events_today: int
    unique_event_names: int
    data_sources: int
