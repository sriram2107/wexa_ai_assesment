"""
Dashboard service: CRUD dashboards, widgets, saved queries,
and query execution for chart data.
"""

import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, func, and_, case
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.dashboard import Dashboard, Widget, SavedQuery
from app.models.ingestion import Event
from app.schemas.dashboard import (
    DashboardCreate,
    DashboardUpdate,
    DashboardResponse,
    DashboardDetailResponse,
    WidgetCreate,
    WidgetUpdate,
    WidgetResponse,
    WidgetWithDataResponse,
    SavedQueryCreate,
    SavedQueryResponse,
    QueryResultResponse,
)

import structlog

logger = structlog.get_logger()

# Time range mapping
TIME_RANGES = {
    "1h": timedelta(hours=1),
    "6h": timedelta(hours=6),
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
    "90d": timedelta(days=90),
}

# Time bucket to seconds
TIME_BUCKETS = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "1h": 3600,
    "6h": 21600,
    "1d": 86400,
}


class DashboardService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Dashboards ──────────────────────────────────────────────────

    async def create_dashboard(
        self, org_id: str, req: DashboardCreate, user_id: str
    ) -> DashboardResponse:
        dashboard = Dashboard(
            organization_id=org_id,
            name=req.name,
            description=req.description,
            auto_refresh_seconds=req.auto_refresh_seconds,
            template_type=req.template_type,
            created_by=user_id,
        )
        self.db.add(dashboard)
        await self.db.flush()

        # If template specified, create default widgets
        if req.template_type:
            await self._create_template_widgets(dashboard)

        logger.info("dashboard_created", org_id=org_id, dashboard_id=dashboard.id)
        return self._dashboard_to_response(dashboard, 0)

    async def list_dashboards(self, org_id: str) -> list[DashboardResponse]:
        result = await self.db.execute(
            select(Dashboard)
            .where(Dashboard.organization_id == org_id)
            .order_by(Dashboard.updated_at.desc())
        )
        dashboards = result.scalars().all()
        responses = []
        for d in dashboards:
            wc = await self.db.execute(
                select(func.count(Widget.id)).where(Widget.dashboard_id == d.id)
            )
            responses.append(self._dashboard_to_response(d, wc.scalar() or 0))
        return responses

    async def get_dashboard(self, org_id: str, dashboard_id: str) -> DashboardDetailResponse:
        result = await self.db.execute(
            select(Dashboard)
            .options(selectinload(Dashboard.widgets).selectinload(Widget.saved_query))
            .where(
                Dashboard.id == dashboard_id,
                Dashboard.organization_id == org_id,
            )
        )
        dashboard = result.scalar_one_or_none()
        if not dashboard:
            raise ValueError("Dashboard not found")

        # Execute query for each widget
        widgets_with_data = []
        for widget in dashboard.widgets:
            data = await self._execute_widget_query(org_id, widget)
            wr = WidgetWithDataResponse(
                id=widget.id,
                dashboard_id=widget.dashboard_id,
                saved_query_id=widget.saved_query_id,
                widget_type=widget.widget_type,
                title=widget.title,
                config=widget.config,
                grid_x=widget.grid_x,
                grid_y=widget.grid_y,
                grid_w=widget.grid_w,
                grid_h=widget.grid_h,
                created_at=widget.created_at,
                data=data,
            )
            widgets_with_data.append(wr)

        return DashboardDetailResponse(
            id=dashboard.id,
            name=dashboard.name,
            description=dashboard.description,
            is_public=dashboard.is_public,
            public_token=dashboard.public_token,
            auto_refresh_seconds=dashboard.auto_refresh_seconds,
            template_type=dashboard.template_type,
            created_by=dashboard.created_by,
            created_at=dashboard.created_at,
            updated_at=dashboard.updated_at,
            widget_count=len(widgets_with_data),
            widgets=widgets_with_data,
        )

    async def get_public_dashboard(self, public_token: str) -> DashboardDetailResponse:
        """Get a dashboard by its public sharing token."""
        result = await self.db.execute(
            select(Dashboard)
            .options(selectinload(Dashboard.widgets).selectinload(Widget.saved_query))
            .where(Dashboard.public_token == public_token, Dashboard.is_public == True)
        )
        dashboard = result.scalar_one_or_none()
        if not dashboard:
            raise ValueError("Dashboard not found")

        widgets_with_data = []
        for widget in dashboard.widgets:
            data = await self._execute_widget_query(dashboard.organization_id, widget)
            wr = WidgetWithDataResponse(
                id=widget.id,
                dashboard_id=widget.dashboard_id,
                saved_query_id=widget.saved_query_id,
                widget_type=widget.widget_type,
                title=widget.title,
                config=widget.config,
                grid_x=widget.grid_x,
                grid_y=widget.grid_y,
                grid_w=widget.grid_w,
                grid_h=widget.grid_h,
                created_at=widget.created_at,
                data=data,
            )
            widgets_with_data.append(wr)

        return DashboardDetailResponse(
            id=dashboard.id,
            name=dashboard.name,
            description=dashboard.description,
            is_public=dashboard.is_public,
            public_token=dashboard.public_token,
            auto_refresh_seconds=dashboard.auto_refresh_seconds,
            template_type=dashboard.template_type,
            created_by=dashboard.created_by,
            created_at=dashboard.created_at,
            updated_at=dashboard.updated_at,
            widget_count=len(widgets_with_data),
            widgets=widgets_with_data,
        )

    async def update_dashboard(
        self, org_id: str, dashboard_id: str, req: DashboardUpdate
    ) -> DashboardResponse:
        result = await self.db.execute(
            select(Dashboard).where(
                Dashboard.id == dashboard_id,
                Dashboard.organization_id == org_id,
            )
        )
        dashboard = result.scalar_one_or_none()
        if not dashboard:
            raise ValueError("Dashboard not found")

        if req.name is not None:
            dashboard.name = req.name
        if req.description is not None:
            dashboard.description = req.description
        if req.auto_refresh_seconds is not None:
            dashboard.auto_refresh_seconds = req.auto_refresh_seconds
        if req.is_public is not None:
            dashboard.is_public = req.is_public
            if req.is_public and not dashboard.public_token:
                dashboard.public_token = secrets.token_urlsafe(16)
            elif not req.is_public:
                dashboard.public_token = None

        dashboard.updated_at = datetime.now(timezone.utc)
        await self.db.flush()

        wc = await self.db.execute(
            select(func.count(Widget.id)).where(Widget.dashboard_id == dashboard.id)
        )
        return self._dashboard_to_response(dashboard, wc.scalar() or 0)

    async def delete_dashboard(self, org_id: str, dashboard_id: str) -> None:
        result = await self.db.execute(
            select(Dashboard).where(
                Dashboard.id == dashboard_id,
                Dashboard.organization_id == org_id,
            )
        )
        dashboard = result.scalar_one_or_none()
        if not dashboard:
            raise ValueError("Dashboard not found")
        await self.db.delete(dashboard)
        await self.db.flush()

    # ── Widgets ─────────────────────────────────────────────────────

    async def add_widget(
        self, org_id: str, dashboard_id: str, req: WidgetCreate, user_id: str
    ) -> WidgetWithDataResponse:
        # Verify dashboard belongs to org
        result = await self.db.execute(
            select(Dashboard).where(
                Dashboard.id == dashboard_id,
                Dashboard.organization_id == org_id,
            )
        )
        if not result.scalar_one_or_none():
            raise ValueError("Dashboard not found")

        # Create saved query if inline query provided
        saved_query_id = req.saved_query_id
        if not saved_query_id and req.event_name:
            sq = SavedQuery(
                organization_id=org_id,
                name=f"{req.title} Query",
                event_name=req.event_name,
                aggregation=req.aggregation,
                aggregation_field=req.aggregation_field,
                group_by=req.group_by,
                filters=req.filters,
                time_range=req.time_range,
                time_bucket=req.time_bucket,
                created_by=user_id,
            )
            self.db.add(sq)
            await self.db.flush()
            saved_query_id = sq.id

        widget = Widget(
            dashboard_id=dashboard_id,
            saved_query_id=saved_query_id,
            widget_type=req.widget_type,
            title=req.title,
            config=req.config,
            grid_x=req.grid_x,
            grid_y=req.grid_y,
            grid_w=req.grid_w,
            grid_h=req.grid_h,
        )
        self.db.add(widget)
        await self.db.flush()

        # Load saved query for execution
        if saved_query_id:
            sq_result = await self.db.execute(
                select(SavedQuery).where(SavedQuery.id == saved_query_id)
            )
            widget.saved_query = sq_result.scalar_one_or_none()

        data = await self._execute_widget_query(org_id, widget)

        return WidgetWithDataResponse(
            id=widget.id,
            dashboard_id=widget.dashboard_id,
            saved_query_id=widget.saved_query_id,
            widget_type=widget.widget_type,
            title=widget.title,
            config=widget.config,
            grid_x=widget.grid_x,
            grid_y=widget.grid_y,
            grid_w=widget.grid_w,
            grid_h=widget.grid_h,
            created_at=widget.created_at,
            data=data,
        )

    async def update_widget(
        self, org_id: str, dashboard_id: str, widget_id: str, req: WidgetUpdate
    ) -> WidgetResponse:
        result = await self.db.execute(
            select(Widget)
            .join(Dashboard)
            .where(
                Widget.id == widget_id,
                Widget.dashboard_id == dashboard_id,
                Dashboard.organization_id == org_id,
            )
        )
        widget = result.scalar_one_or_none()
        if not widget:
            raise ValueError("Widget not found")

        for field, value in req.model_dump(exclude_unset=True).items():
            setattr(widget, field, value)

        widget.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        return WidgetResponse.model_validate(widget)

    async def delete_widget(self, org_id: str, dashboard_id: str, widget_id: str) -> None:
        result = await self.db.execute(
            select(Widget)
            .join(Dashboard)
            .where(
                Widget.id == widget_id,
                Widget.dashboard_id == dashboard_id,
                Dashboard.organization_id == org_id,
            )
        )
        widget = result.scalar_one_or_none()
        if not widget:
            raise ValueError("Widget not found")
        await self.db.delete(widget)
        await self.db.flush()

    # ── Saved Queries ───────────────────────────────────────────────

    async def create_saved_query(
        self, org_id: str, req: SavedQueryCreate, user_id: str
    ) -> SavedQueryResponse:
        sq = SavedQuery(
            organization_id=org_id,
            name=req.name,
            event_name=req.event_name,
            aggregation=req.aggregation,
            aggregation_field=req.aggregation_field,
            group_by=req.group_by,
            filters=req.filters,
            time_range=req.time_range,
            time_bucket=req.time_bucket,
            created_by=user_id,
        )
        self.db.add(sq)
        await self.db.flush()
        return SavedQueryResponse.model_validate(sq)

    async def execute_query(self, org_id: str, query_id: str) -> QueryResultResponse:
        result = await self.db.execute(
            select(SavedQuery).where(
                SavedQuery.id == query_id,
                SavedQuery.organization_id == org_id,
            )
        )
        sq = result.scalar_one_or_none()
        if not sq:
            raise ValueError("Query not found")

        return await self._run_query(org_id, sq)

    # ── Query Execution Engine ──────────────────────────────────────

    async def _execute_widget_query(self, org_id: str, widget: Widget) -> Optional[QueryResultResponse]:
        """Execute the query associated with a widget."""
        if widget.saved_query:
            return await self._run_query(org_id, widget.saved_query)

        # No query attached — return empty data
        return QueryResultResponse(labels=[], datasets=[], summary={})

    async def _run_query(self, org_id: str, sq: SavedQuery) -> QueryResultResponse:
        """Execute a saved query and return chart-ready data."""
        now = datetime.now(timezone.utc)
        time_delta = TIME_RANGES.get(sq.time_range, timedelta(days=7))
        start_time = now - time_delta
        bucket_seconds = TIME_BUCKETS.get(sq.time_bucket, 3600)

        # Base query with org isolation and time filter
        base_filter = and_(
            Event.organization_id == org_id,
            Event.event_name == sq.event_name,
            Event.timestamp >= start_time,
            Event.timestamp <= now,
        )

        # For KPI widgets, just compute a single aggregate
        if sq.group_by is None:
            # Time-series data
            result = await self.db.execute(
                select(Event)
                .where(base_filter)
                .order_by(Event.timestamp.asc())
            )
            events = result.scalars().all()

            # Bucket events into time windows
            buckets = {}
            for event in events:
                bucket_key = int(event.timestamp.timestamp()) // bucket_seconds * bucket_seconds
                bucket_dt = datetime.fromtimestamp(bucket_key, tz=timezone.utc)
                label = bucket_dt.strftime("%Y-%m-%d %H:%M")

                if label not in buckets:
                    buckets[label] = []
                buckets[label].append(event)

            labels = sorted(buckets.keys())
            values = []
            for label in labels:
                bucket_events = buckets[label]
                values.append(self._aggregate(bucket_events, sq.aggregation, sq.aggregation_field))

            # Compute summary
            total = await self.db.execute(
                select(func.count(Event.id)).where(base_filter)
            )
            summary = {"total": total.scalar() or 0}
            if sq.aggregation == "sum" and sq.aggregation_field:
                sum_result = await self.db.execute(
                    select(func.sum(Event.numeric_value)).where(base_filter)
                )
                summary["sum"] = sum_result.scalar() or 0
            if sq.aggregation == "avg" and sq.aggregation_field:
                avg_result = await self.db.execute(
                    select(func.avg(Event.numeric_value)).where(base_filter)
                )
                summary["avg"] = round(avg_result.scalar() or 0, 2)

            return QueryResultResponse(
                labels=labels,
                datasets=[{"label": sq.event_name, "data": values}],
                summary=summary,
            )
        else:
            # Grouped data (for pie/bar charts)
            result = await self.db.execute(
                select(Event).where(base_filter).order_by(Event.timestamp.asc())
            )
            events = result.scalars().all()

            groups = {}
            for event in events:
                group_val = event.properties.get(sq.group_by, "unknown") if event.properties else "unknown"
                if group_val not in groups:
                    groups[group_val] = []
                groups[group_val].append(event)

            labels = list(groups.keys())
            values = [
                self._aggregate(groups[label], sq.aggregation, sq.aggregation_field)
                for label in labels
            ]

            return QueryResultResponse(
                labels=labels,
                datasets=[{"label": sq.event_name, "data": values}],
                summary={"groups": len(labels)},
            )

    def _aggregate(self, events: list, aggregation: str, field: str = None) -> float:
        """Compute aggregation over a list of events."""
        if aggregation == "count":
            return len(events)
        elif aggregation == "sum":
            return sum(e.numeric_value or 0 for e in events)
        elif aggregation == "avg":
            vals = [e.numeric_value for e in events if e.numeric_value is not None]
            return round(sum(vals) / len(vals), 2) if vals else 0
        elif aggregation == "min":
            vals = [e.numeric_value for e in events if e.numeric_value is not None]
            return min(vals) if vals else 0
        elif aggregation == "max":
            vals = [e.numeric_value for e in events if e.numeric_value is not None]
            return max(vals) if vals else 0
        return len(events)

    # ── Template Widgets ────────────────────────────────────────────

    async def _create_template_widgets(self, dashboard: Dashboard) -> None:
        """Create default widgets for a dashboard template."""
        templates = {
            "web_analytics": [
                {"title": "Page Views", "type": "kpi", "event": "page_view", "agg": "count"},
                {"title": "Page Views Over Time", "type": "line", "event": "page_view", "agg": "count"},
                {"title": "Top Pages", "type": "bar", "event": "page_view", "agg": "count", "group": "page"},
                {"title": "Traffic Sources", "type": "pie", "event": "page_view", "agg": "count", "group": "source"},
            ],
            "sales": [
                {"title": "Total Revenue", "type": "kpi", "event": "purchase", "agg": "sum", "field": "numeric_value"},
                {"title": "Revenue Over Time", "type": "line", "event": "purchase", "agg": "sum", "field": "numeric_value"},
                {"title": "Sales by Product", "type": "bar", "event": "purchase", "agg": "count", "group": "product"},
                {"title": "Payment Methods", "type": "pie", "event": "purchase", "agg": "count", "group": "method"},
            ],
            "devops": [
                {"title": "Total Errors", "type": "kpi", "event": "error", "agg": "count"},
                {"title": "Errors Over Time", "type": "line", "event": "error", "agg": "count"},
                {"title": "Errors by Service", "type": "bar", "event": "error", "agg": "count", "group": "service"},
                {"title": "Error Types", "type": "pie", "event": "error", "agg": "count", "group": "type"},
            ],
        }

        template_config = templates.get(dashboard.template_type, [])
        for i, t in enumerate(template_config):
            sq = SavedQuery(
                organization_id=dashboard.organization_id,
                name=t["title"],
                event_name=t["event"],
                aggregation=t["agg"],
                aggregation_field=t.get("field"),
                group_by=t.get("group"),
                time_range="7d",
                time_bucket="1h" if t["type"] != "kpi" else "1d",
                created_by=dashboard.created_by,
            )
            self.db.add(sq)
            await self.db.flush()

            widget = Widget(
                dashboard_id=dashboard.id,
                saved_query_id=sq.id,
                widget_type=t["type"],
                title=t["title"],
                grid_x=(i % 2) * 6,
                grid_y=(i // 2) * 4,
                grid_w=6 if t["type"] != "kpi" else 3,
                grid_h=4 if t["type"] != "kpi" else 2,
            )
            self.db.add(widget)

        await self.db.flush()

    # ── Helpers ─────────────────────────────────────────────────────

    def _dashboard_to_response(self, d: Dashboard, widget_count: int) -> DashboardResponse:
        return DashboardResponse(
            id=d.id,
            name=d.name,
            description=d.description,
            is_public=d.is_public,
            public_token=d.public_token,
            auto_refresh_seconds=d.auto_refresh_seconds,
            template_type=d.template_type,
            created_by=d.created_by,
            created_at=d.created_at,
            updated_at=d.updated_at,
            widget_count=widget_count,
        )
