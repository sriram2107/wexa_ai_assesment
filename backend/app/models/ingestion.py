"""
Event ingestion, DataSource, and API Key models.
Optimized for time-series event storage.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def utcnow():
    return datetime.now(timezone.utc)


def generate_uuid():
    return str(uuid.uuid4())


class DataSource(Base):
    __tablename__ = "data_sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    organization_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)  # api, csv, webhook
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    events: Mapped[list["Event"]] = relationship(back_populates="data_source", cascade="all, delete-orphan")


class Event(Base):
    """
    Core event table for analytics data.
    Indexed on (organization_id, event_name, timestamp) for efficient time-series queries.
    """
    __tablename__ = "events"
    __table_args__ = (
        Index("ix_events_org_name_ts", "organization_id", "event_name", "timestamp"),
        Index("ix_events_org_ts", "organization_id", "timestamp"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    organization_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"), nullable=False)
    data_source_id: Mapped[str] = mapped_column(String(36), ForeignKey("data_sources.id"), nullable=True)
    event_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    properties: Mapped[dict] = mapped_column(JSON, default=dict)
    user_id_ext: Mapped[str] = mapped_column(String(255), nullable=True)  # external user identifier
    session_id: Mapped[str] = mapped_column(String(255), nullable=True)
    numeric_value: Mapped[float] = mapped_column(Float, nullable=True)  # for metric aggregation
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    data_source: Mapped["DataSource"] = relationship(back_populates="events")


class APIKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    organization_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    key_prefix: Mapped[str] = mapped_column(String(10), nullable=False)  # first 8 chars for display
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    revoked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
