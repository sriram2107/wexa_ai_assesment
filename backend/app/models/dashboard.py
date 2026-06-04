"""
Dashboard, Widget, and SavedQuery models.
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


class Dashboard(Base):
    __tablename__ = "dashboards"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    organization_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)
    public_token: Mapped[str] = mapped_column(String(64), unique=True, nullable=True)
    auto_refresh_seconds: Mapped[int] = mapped_column(Integer, default=0)  # 0 = disabled
    layout: Mapped[dict] = mapped_column(JSON, default=dict)  # grid layout config
    template_type: Mapped[str] = mapped_column(String(50), nullable=True)  # web_analytics, sales, devops
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    widgets: Mapped[list["Widget"]] = relationship(back_populates="dashboard", cascade="all, delete-orphan")


class SavedQuery(Base):
    __tablename__ = "saved_queries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    organization_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    event_name: Mapped[str] = mapped_column(String(255), nullable=False)
    aggregation: Mapped[str] = mapped_column(String(50), default="count")  # count, sum, avg, min, max
    aggregation_field: Mapped[str] = mapped_column(String(255), nullable=True)  # field for sum/avg/min/max
    group_by: Mapped[str] = mapped_column(String(255), nullable=True)  # property field to group by
    filters: Mapped[dict] = mapped_column(JSON, default=dict)
    time_range: Mapped[str] = mapped_column(String(50), default="7d")  # 1h, 24h, 7d, 30d, 90d, custom
    time_bucket: Mapped[str] = mapped_column(String(20), default="1h")  # 1m, 5m, 1h, 1d
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    widgets: Mapped[list["Widget"]] = relationship(back_populates="saved_query")


class Widget(Base):
    __tablename__ = "widgets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    dashboard_id: Mapped[str] = mapped_column(String(36), ForeignKey("dashboards.id"), nullable=False, index=True)
    saved_query_id: Mapped[str] = mapped_column(String(36), ForeignKey("saved_queries.id"), nullable=True)
    widget_type: Mapped[str] = mapped_column(String(50), nullable=False)  # line, bar, pie, kpi, table
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    config: Mapped[dict] = mapped_column(JSON, default=dict)  # chart-specific config (colors, labels, etc.)
    # Grid position
    grid_x: Mapped[int] = mapped_column(Integer, default=0)
    grid_y: Mapped[int] = mapped_column(Integer, default=0)
    grid_w: Mapped[int] = mapped_column(Integer, default=6)
    grid_h: Mapped[int] = mapped_column(Integer, default=4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    dashboard: Mapped["Dashboard"] = relationship(back_populates="widgets")
    saved_query: Mapped["SavedQuery"] = relationship(back_populates="widgets")
