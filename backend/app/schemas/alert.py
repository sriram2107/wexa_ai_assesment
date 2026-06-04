"""
Pydantic v2 schemas for alerts and notification channels.
"""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ── Notification Channels ───────────────────────────────────────────

class NotificationChannelCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    channel_type: str = Field(pattern="^(email|webhook|in_app)$")
    config: dict[str, Any] = Field(default_factory=dict)


class NotificationChannelResponse(BaseModel):
    id: str
    name: str
    channel_type: str
    config: dict[str, Any]
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Alert Rules ─────────────────────────────────────────────────────

class AlertRuleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    event_name: str = Field(min_length=1, max_length=255)
    metric: str = Field(default="count", pattern="^(count|sum|avg)$")
    aggregation_field: Optional[str] = None
    condition: str = Field(pattern="^(gt|lt|gte|lte|eq)$")
    threshold: float
    window_minutes: int = Field(default=10, ge=1, le=1440)
    evaluation_interval_minutes: int = Field(default=5, ge=1, le=60)
    notification_channels: list[str] = Field(default_factory=list)


class AlertRuleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    threshold: Optional[float] = None
    window_minutes: Optional[int] = None
    status: Optional[str] = None


class AlertRuleResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    event_name: str
    metric: str
    condition: str
    threshold: float
    window_minutes: int
    evaluation_interval_minutes: int
    status: str
    notification_channels: Any
    created_at: datetime
    last_evaluated_at: Optional[datetime] = None
    last_triggered_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class MuteAlertRequest(BaseModel):
    mute_minutes: int = Field(ge=1, le=10080)  # up to 7 days


# ── Alert History ───────────────────────────────────────────────────

class AlertHistoryResponse(BaseModel):
    id: str
    alert_rule_id: str
    status: str
    triggered_value: Optional[float] = None
    message: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}
