"""
Alert management endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.core.database import get_db
from app.core.security import get_current_user_with_org, require_analyst
from app.schemas.alert import (
    AlertRuleCreate,
    AlertRuleUpdate,
    AlertRuleResponse,
    AlertHistoryResponse,
    MuteAlertRequest,
    NotificationChannelCreate,
    NotificationChannelResponse,
)
from app.services.alert_service import AlertService

router = APIRouter(prefix="/alerts", tags=["Alerts & Notifications"])


@router.post("/rules", response_model=AlertRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_alert_rule(
    req: AlertRuleCreate,
    user=Depends(require_analyst),
    db: AsyncSession = Depends(get_db),
):
    """Create a new alert rule."""
    service = AlertService(db)
    return await service.create_alert_rule(
        user.current_membership.organization_id, req, user.id
    )


@router.get("/rules", response_model=list[AlertRuleResponse])
async def list_alert_rules(
    user=Depends(get_current_user_with_org),
    db: AsyncSession = Depends(get_db),
):
    """List all alert rules for the organization."""
    service = AlertService(db)
    return await service.list_alert_rules(user.current_membership.organization_id)


@router.get("/rules/{rule_id}", response_model=AlertRuleResponse)
async def get_alert_rule(
    rule_id: str,
    user=Depends(get_current_user_with_org),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific alert rule."""
    try:
        service = AlertService(db)
        return await service.get_alert_rule(
            user.current_membership.organization_id, rule_id
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.patch("/rules/{rule_id}", response_model=AlertRuleResponse)
async def update_alert_rule(
    rule_id: str,
    req: AlertRuleUpdate,
    user=Depends(require_analyst),
    db: AsyncSession = Depends(get_db),
):
    """Update an alert rule."""
    try:
        service = AlertService(db)
        return await service.update_alert_rule(
            user.current_membership.organization_id, rule_id, req
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_alert_rule(
    rule_id: str,
    user=Depends(require_analyst),
    db: AsyncSession = Depends(get_db),
):
    """Delete an alert rule."""
    try:
        service = AlertService(db)
        await service.delete_alert_rule(
            user.current_membership.organization_id, rule_id
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/rules/{rule_id}/mute", response_model=AlertRuleResponse)
async def mute_alert(
    rule_id: str,
    req: MuteAlertRequest,
    user=Depends(require_analyst),
    db: AsyncSession = Depends(get_db),
):
    """Mute an alert for a specified duration."""
    try:
        service = AlertService(db)
        return await service.mute_alert(
            user.current_membership.organization_id, rule_id, req.mute_minutes
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/history", response_model=list[AlertHistoryResponse])
async def get_alert_history(
    rule_id: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    user=Depends(get_current_user_with_org),
    db: AsyncSession = Depends(get_db),
):
    """Get alert history for the organization."""
    service = AlertService(db)
    return await service.get_alert_history(
        user.current_membership.organization_id, rule_id, limit
    )


# ── Notification Channels ──────────────────────────────────────────

@router.post("/channels", response_model=NotificationChannelResponse, status_code=status.HTTP_201_CREATED)
async def create_channel(
    req: NotificationChannelCreate,
    user=Depends(require_analyst),
    db: AsyncSession = Depends(get_db),
):
    """Create a notification channel."""
    service = AlertService(db)
    return await service.create_channel(
        user.current_membership.organization_id, req
    )


@router.get("/channels", response_model=list[NotificationChannelResponse])
async def list_channels(
    user=Depends(get_current_user_with_org),
    db: AsyncSession = Depends(get_db),
):
    """List notification channels."""
    service = AlertService(db)
    return await service.list_channels(user.current_membership.organization_id)


# ── Manual Evaluation (for testing) ─────────────────────────────────

@router.post("/evaluate")
async def evaluate_alerts(
    user=Depends(require_analyst),
    db: AsyncSession = Depends(get_db),
):
    """Manually trigger alert evaluation (for testing)."""
    service = AlertService(db)
    triggered = await service.evaluate_all_alerts()
    return {"evaluated": True, "triggered": triggered}
