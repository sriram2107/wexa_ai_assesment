"""
Alert service: CRUD alert rules, alert evaluation, notification dispatch.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import AlertRule, AlertHistory, NotificationChannel
from app.models.ingestion import Event
from app.schemas.alert import (
    AlertRuleCreate,
    AlertRuleUpdate,
    AlertRuleResponse,
    AlertHistoryResponse,
    NotificationChannelCreate,
    NotificationChannelResponse,
)

import structlog

logger = structlog.get_logger()

CONDITION_OPS = {
    "gt": lambda v, t: v > t,
    "lt": lambda v, t: v < t,
    "gte": lambda v, t: v >= t,
    "lte": lambda v, t: v <= t,
    "eq": lambda v, t: v == t,
}


class AlertService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Alert Rules ─────────────────────────────────────────────────

    async def create_alert_rule(
        self, org_id: str, req: AlertRuleCreate, user_id: str
    ) -> AlertRuleResponse:
        rule = AlertRule(
            organization_id=org_id,
            name=req.name,
            description=req.description,
            event_name=req.event_name,
            metric=req.metric,
            aggregation_field=req.aggregation_field,
            condition=req.condition,
            threshold=req.threshold,
            window_minutes=req.window_minutes,
            evaluation_interval_minutes=req.evaluation_interval_minutes,
            notification_channels=req.notification_channels,
            created_by=user_id,
        )
        self.db.add(rule)
        await self.db.flush()
        logger.info("alert_rule_created", org_id=org_id, rule_id=rule.id)
        return AlertRuleResponse.model_validate(rule)

    async def list_alert_rules(self, org_id: str) -> list[AlertRuleResponse]:
        result = await self.db.execute(
            select(AlertRule)
            .where(AlertRule.organization_id == org_id)
            .order_by(AlertRule.created_at.desc())
        )
        return [AlertRuleResponse.model_validate(r) for r in result.scalars().all()]

    async def get_alert_rule(self, org_id: str, rule_id: str) -> AlertRuleResponse:
        result = await self.db.execute(
            select(AlertRule).where(
                AlertRule.id == rule_id,
                AlertRule.organization_id == org_id,
            )
        )
        rule = result.scalar_one_or_none()
        if not rule:
            raise ValueError("Alert rule not found")
        return AlertRuleResponse.model_validate(rule)

    async def update_alert_rule(
        self, org_id: str, rule_id: str, req: AlertRuleUpdate
    ) -> AlertRuleResponse:
        result = await self.db.execute(
            select(AlertRule).where(
                AlertRule.id == rule_id,
                AlertRule.organization_id == org_id,
            )
        )
        rule = result.scalar_one_or_none()
        if not rule:
            raise ValueError("Alert rule not found")

        for field, value in req.model_dump(exclude_unset=True).items():
            setattr(rule, field, value)

        rule.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        return AlertRuleResponse.model_validate(rule)

    async def delete_alert_rule(self, org_id: str, rule_id: str) -> None:
        result = await self.db.execute(
            select(AlertRule).where(
                AlertRule.id == rule_id,
                AlertRule.organization_id == org_id,
            )
        )
        rule = result.scalar_one_or_none()
        if not rule:
            raise ValueError("Alert rule not found")
        await self.db.delete(rule)
        await self.db.flush()

    async def mute_alert(self, org_id: str, rule_id: str, mute_minutes: int) -> AlertRuleResponse:
        result = await self.db.execute(
            select(AlertRule).where(
                AlertRule.id == rule_id,
                AlertRule.organization_id == org_id,
            )
        )
        rule = result.scalar_one_or_none()
        if not rule:
            raise ValueError("Alert rule not found")

        rule.status = "muted"
        rule.muted_until = datetime.now(timezone.utc) + timedelta(minutes=mute_minutes)
        await self.db.flush()
        return AlertRuleResponse.model_validate(rule)

    # ── Alert History ───────────────────────────────────────────────

    async def get_alert_history(
        self, org_id: str, rule_id: str = None, limit: int = 50
    ) -> list[AlertHistoryResponse]:
        query = select(AlertHistory).where(AlertHistory.organization_id == org_id)
        if rule_id:
            query = query.where(AlertHistory.alert_rule_id == rule_id)
        query = query.order_by(AlertHistory.created_at.desc()).limit(limit)

        result = await self.db.execute(query)
        return [AlertHistoryResponse.model_validate(h) for h in result.scalars().all()]

    # ── Alert Evaluation ────────────────────────────────────────────

    async def evaluate_all_alerts(self) -> list[dict]:
        """Evaluate all active alert rules. Called by background task."""
        now = datetime.now(timezone.utc)
        result = await self.db.execute(
            select(AlertRule).where(AlertRule.status.in_(["active", "triggered"]))
        )
        rules = result.scalars().all()

        triggered = []
        for rule in rules:
            # Check mute
            if rule.muted_until and rule.muted_until > now:
                continue

            # Un-mute if past mute time
            if rule.status == "muted" and rule.muted_until and rule.muted_until <= now:
                rule.status = "active"

            try:
                was_triggered = await self._evaluate_rule(rule, now)
                if was_triggered:
                    triggered.append({"rule_id": rule.id, "name": rule.name})
            except Exception as e:
                logger.error("alert_evaluation_error", rule_id=rule.id, error=str(e))

        await self.db.flush()
        return triggered

    async def _evaluate_rule(self, rule: AlertRule, now: datetime) -> bool:
        """Evaluate a single alert rule and return True if triggered."""
        window_start = now - timedelta(minutes=rule.window_minutes)

        base_filter = and_(
            Event.organization_id == rule.organization_id,
            Event.event_name == rule.event_name,
            Event.timestamp >= window_start,
            Event.timestamp <= now,
        )

        # Compute metric
        if rule.metric == "count":
            result = await self.db.execute(
                select(func.count(Event.id)).where(base_filter)
            )
            value = result.scalar() or 0
        elif rule.metric == "sum":
            result = await self.db.execute(
                select(func.sum(Event.numeric_value)).where(base_filter)
            )
            value = result.scalar() or 0
        elif rule.metric == "avg":
            result = await self.db.execute(
                select(func.avg(Event.numeric_value)).where(base_filter)
            )
            value = result.scalar() or 0
        else:
            value = 0

        # Check condition
        check_fn = CONDITION_OPS.get(rule.condition, lambda v, t: False)
        is_triggered = check_fn(value, rule.threshold)

        rule.last_evaluated_at = now

        if is_triggered and rule.status != "triggered":
            rule.status = "triggered"
            rule.last_triggered_at = now

            # Create history entry
            history = AlertHistory(
                alert_rule_id=rule.id,
                organization_id=rule.organization_id,
                status="triggered",
                triggered_value=float(value),
                message=f"{rule.metric} of '{rule.event_name}' is {value} "
                        f"(threshold: {rule.condition} {rule.threshold})",
            )
            self.db.add(history)

            logger.warning(
                "alert_triggered",
                rule_id=rule.id,
                value=value,
                threshold=rule.threshold,
            )
            return True

        elif not is_triggered and rule.status == "triggered":
            rule.status = "resolved"
            history = AlertHistory(
                alert_rule_id=rule.id,
                organization_id=rule.organization_id,
                status="resolved",
                triggered_value=float(value),
                message=f"Alert resolved: {rule.metric} of '{rule.event_name}' is {value}",
            )
            self.db.add(history)
            # Reset to active after resolving
            rule.status = "active"
            logger.info("alert_resolved", rule_id=rule.id, value=value)

        return False

    # ── Notification Channels ───────────────────────────────────────

    async def create_channel(
        self, org_id: str, req: NotificationChannelCreate
    ) -> NotificationChannelResponse:
        channel = NotificationChannel(
            organization_id=org_id,
            name=req.name,
            channel_type=req.channel_type,
            config=req.config,
        )
        self.db.add(channel)
        await self.db.flush()
        return NotificationChannelResponse.model_validate(channel)

    async def list_channels(self, org_id: str) -> list[NotificationChannelResponse]:
        result = await self.db.execute(
            select(NotificationChannel).where(
                NotificationChannel.organization_id == org_id
            )
        )
        return [NotificationChannelResponse.model_validate(c) for c in result.scalars().all()]
