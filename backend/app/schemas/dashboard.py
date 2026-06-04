"""
Pydantic v2 schemas for dashboards, widgets, and saved queries.
"""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ── Saved Queries ───────────────────────────────────────────────────

class SavedQueryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    event_name: str = Field(min_length=1, max_length=255)
    aggregation: str = Field(default="count", pattern="^(count|sum|avg|min|max)$")
    aggregation_field: Optional[str] = None
    group_by: Optional[str] = None
    filters: dict[str, Any] = Field(default_factory=dict)
    time_range: str = Field(default="7d")
    time_bucket: str = Field(default="1h")


class SavedQueryResponse(BaseModel):
    id: str
    name: str
    event_name: str
    aggregation: str
    aggregation_field: Optional[str] = None
    group_by: Optional[str] = None
    filters: dict[str, Any]
    time_range: str
    time_bucket: str
    created_at: datetime

    model_config = {"from_attributes": True}


class QueryResultResponse(BaseModel):
    """Result of executing a saved query — time-series data points."""
    labels: list[str]
    datasets: list[dict[str, Any]]
    summary: dict[str, Any] = Field(default_factory=dict)


# ── Widgets ─────────────────────────────────────────────────────────

class WidgetCreate(BaseModel):
    widget_type: str = Field(pattern="^(line|bar|pie|kpi|table)$")
    title: str = Field(min_length=1, max_length=255)
    saved_query_id: Optional[str] = None
    config: dict[str, Any] = Field(default_factory=dict)
    grid_x: int = Field(default=0, ge=0)
    grid_y: int = Field(default=0, ge=0)
    grid_w: int = Field(default=6, ge=1, le=12)
    grid_h: int = Field(default=4, ge=1, le=12)
    # Inline query definition (used if saved_query_id is not provided)
    event_name: Optional[str] = None
    aggregation: str = "count"
    aggregation_field: Optional[str] = None
    group_by: Optional[str] = None
    filters: dict[str, Any] = Field(default_factory=dict)
    time_range: str = "7d"
    time_bucket: str = "1h"


class WidgetUpdate(BaseModel):
    title: Optional[str] = None
    config: Optional[dict[str, Any]] = None
    grid_x: Optional[int] = None
    grid_y: Optional[int] = None
    grid_w: Optional[int] = None
    grid_h: Optional[int] = None


class WidgetResponse(BaseModel):
    id: str
    dashboard_id: str
    saved_query_id: Optional[str] = None
    widget_type: str
    title: str
    config: dict[str, Any]
    grid_x: int
    grid_y: int
    grid_w: int
    grid_h: int
    created_at: datetime

    model_config = {"from_attributes": True}


class WidgetWithDataResponse(WidgetResponse):
    data: Optional[QueryResultResponse] = None


# ── Dashboards ──────────────────────────────────────────────────────

class DashboardCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    auto_refresh_seconds: int = Field(default=0, ge=0)
    template_type: Optional[str] = None


class DashboardUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    auto_refresh_seconds: Optional[int] = None
    is_public: Optional[bool] = None


class DashboardResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    is_public: bool
    public_token: Optional[str] = None
    auto_refresh_seconds: int
    template_type: Optional[str] = None
    created_by: str
    created_at: datetime
    updated_at: datetime
    widget_count: int = 0

    model_config = {"from_attributes": True}


class DashboardDetailResponse(DashboardResponse):
    widgets: list[WidgetWithDataResponse] = []
