"""
Dashboard & widget management endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user_with_org, require_analyst, require_admin, require_viewer
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
from app.services.dashboard_service import DashboardService

router = APIRouter(prefix="/dashboards", tags=["Dashboards"])


@router.post("/", response_model=DashboardResponse, status_code=status.HTTP_201_CREATED)
async def create_dashboard(
    req: DashboardCreate,
    user=Depends(require_analyst),
    db: AsyncSession = Depends(get_db),
):
    """Create a new dashboard (analyst+ only)."""
    service = DashboardService(db)
    return await service.create_dashboard(
        user.current_membership.organization_id, req, user.id
    )


@router.get("/", response_model=list[DashboardResponse])
async def list_dashboards(
    user=Depends(get_current_user_with_org),
    db: AsyncSession = Depends(get_db),
):
    """List all dashboards for the organization."""
    service = DashboardService(db)
    return await service.list_dashboards(user.current_membership.organization_id)


@router.get("/public/{public_token}", response_model=DashboardDetailResponse)
async def get_public_dashboard(
    public_token: str,
    db: AsyncSession = Depends(get_db),
):
    """Get a public dashboard by its sharing token (no auth required)."""
    try:
        service = DashboardService(db)
        return await service.get_public_dashboard(public_token)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{dashboard_id}", response_model=DashboardDetailResponse)
async def get_dashboard(
    dashboard_id: str,
    user=Depends(get_current_user_with_org),
    db: AsyncSession = Depends(get_db),
):
    """Get dashboard with all widgets and their data."""
    try:
        service = DashboardService(db)
        return await service.get_dashboard(
            user.current_membership.organization_id, dashboard_id
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.patch("/{dashboard_id}", response_model=DashboardResponse)
async def update_dashboard(
    dashboard_id: str,
    req: DashboardUpdate,
    user=Depends(require_analyst),
    db: AsyncSession = Depends(get_db),
):
    """Update dashboard settings."""
    try:
        service = DashboardService(db)
        return await service.update_dashboard(
            user.current_membership.organization_id, dashboard_id, req
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{dashboard_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_dashboard(
    dashboard_id: str,
    user=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Delete a dashboard (admin+ only)."""
    try:
        service = DashboardService(db)
        await service.delete_dashboard(
            user.current_membership.organization_id, dashboard_id
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── Widgets ─────────────────────────────────────────────────────────

@router.post("/{dashboard_id}/widgets", response_model=WidgetWithDataResponse, status_code=status.HTTP_201_CREATED)
async def add_widget(
    dashboard_id: str,
    req: WidgetCreate,
    user=Depends(require_analyst),
    db: AsyncSession = Depends(get_db),
):
    """Add a widget to a dashboard."""
    try:
        service = DashboardService(db)
        return await service.add_widget(
            user.current_membership.organization_id, dashboard_id, req, user.id
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.patch("/{dashboard_id}/widgets/{widget_id}", response_model=WidgetResponse)
async def update_widget(
    dashboard_id: str,
    widget_id: str,
    req: WidgetUpdate,
    user=Depends(require_analyst),
    db: AsyncSession = Depends(get_db),
):
    """Update widget settings (position, config)."""
    try:
        service = DashboardService(db)
        return await service.update_widget(
            user.current_membership.organization_id, dashboard_id, widget_id, req
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{dashboard_id}/widgets/{widget_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_widget(
    dashboard_id: str,
    widget_id: str,
    user=Depends(require_analyst),
    db: AsyncSession = Depends(get_db),
):
    """Remove a widget from a dashboard."""
    try:
        service = DashboardService(db)
        await service.delete_widget(
            user.current_membership.organization_id, dashboard_id, widget_id
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── Saved Queries ───────────────────────────────────────────────────

@router.post("/queries", response_model=SavedQueryResponse, status_code=status.HTTP_201_CREATED)
async def create_query(
    req: SavedQueryCreate,
    user=Depends(require_analyst),
    db: AsyncSession = Depends(get_db),
):
    """Create a saved query."""
    service = DashboardService(db)
    return await service.create_saved_query(
        user.current_membership.organization_id, req, user.id
    )


@router.get("/queries/{query_id}/execute", response_model=QueryResultResponse)
async def execute_query(
    query_id: str,
    user=Depends(get_current_user_with_org),
    db: AsyncSession = Depends(get_db),
):
    """Execute a saved query and return chart data."""
    try:
        service = DashboardService(db)
        return await service.execute_query(
            user.current_membership.organization_id, query_id
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
