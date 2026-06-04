"""
Alert rules, alert history, and notification channel models.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def utcnow():
    return datetime.now(timezone.utc)


def generate_uuid():
    return str(uuid.uuid4())


class AlertRule(Base):
    __tablename__ = "alert_rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    organization_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    event_name: Mapped[str] = mapped_column(String(255), nullable=False)
    metric: Mapped[str] = mapped_column(String(50), default="count")  # count, sum, avg
    aggregation_field: Mapped[str] = mapped_column(String(255), nullable=True)
    condition: Mapped[str] = mapped_column(String(20), nullable=False)  # gt, lt, gte, lte, eq
    threshold: Mapped[float] = mapped_column(Float, nullable=False)
    window_minutes: Mapped[int] = mapped_column(Integer, default=10)
    evaluation_interval_minutes: Mapped[int] = mapped_column(Integer, default=5)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active, triggered, resolved, muted
    muted_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    notification_channels: Mapped[dict] = mapped_column(JSON, default=list)  # list of channel IDs
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    last_evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    last_triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    history: Mapped[list["AlertHistory"]] = relationship(back_populates="alert_rule", cascade="all, delete-orphan")


class AlertHistory(Base):
    __tablename__ = "alert_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    alert_rule_id: Mapped[str] = mapped_column(String(36), ForeignKey("alert_rules.id"), nullable=False, index=True)
    organization_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # triggered, resolved
    triggered_value: Mapped[float] = mapped_column(Float, nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    alert_rule: Mapped["AlertRule"] = relationship(back_populates="history")


class NotificationChannel(Base):
    __tablename__ = "notification_channels"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    organization_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    channel_type: Mapped[str] = mapped_column(String(50), nullable=False)  # email, webhook, in_app
    config: Mapped[dict] = mapped_column(JSON, default=dict)  # e.g., {"url": "...", "emails": [...]}
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
