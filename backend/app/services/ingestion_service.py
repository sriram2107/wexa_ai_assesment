"""
Event ingestion service: single/batch event processing, CSV upload,
API key management, and ingestion stats.
"""

import csv
import io
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import generate_api_key, hash_api_key
from app.models.ingestion import Event, DataSource, APIKey
from app.schemas.ingestion import (
    EventCreate,
    BatchEventsCreate,
    EventResponse,
    APIKeyCreate,
    APIKeyCreatedResponse,
    APIKeyResponse,
    DataSourceCreate,
    DataSourceResponse,
    IngestionStatsResponse,
)

import structlog

logger = structlog.get_logger()


class IngestionService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Event Ingestion ─────────────────────────────────────────────

    async def ingest_single_event(
        self, org_id: str, event_data: EventCreate, data_source_id: str = None
    ) -> EventResponse:
        """Ingest a single event."""
        event = Event(
            organization_id=org_id,
            data_source_id=data_source_id,
            event_name=event_data.event_name,
            timestamp=event_data.timestamp or datetime.now(timezone.utc),
            properties=event_data.properties,
            user_id_ext=event_data.user_id,
            session_id=event_data.session_id,
            numeric_value=event_data.numeric_value,
        )
        self.db.add(event)
        await self.db.flush()

        logger.info("event_ingested", org_id=org_id, event_name=event_data.event_name)
        return EventResponse.model_validate(event)

    async def ingest_batch_events(
        self, org_id: str, batch: BatchEventsCreate, data_source_id: str = None
    ) -> dict:
        """Ingest a batch of events."""
        events = []
        for event_data in batch.events:
            event = Event(
                organization_id=org_id,
                data_source_id=data_source_id,
                event_name=event_data.event_name,
                timestamp=event_data.timestamp or datetime.now(timezone.utc),
                properties=event_data.properties,
                user_id_ext=event_data.user_id,
                session_id=event_data.session_id,
                numeric_value=event_data.numeric_value,
            )
            events.append(event)

        self.db.add_all(events)
        await self.db.flush()

        logger.info("batch_ingested", org_id=org_id, count=len(events))
        return {"ingested": len(events), "status": "success"}

    async def ingest_csv(self, org_id: str, file_content: bytes, filename: str) -> dict:
        """Parse and ingest events from a CSV file."""
        text = file_content.decode("utf-8")
        reader = csv.DictReader(io.StringIO(text))

        events = []
        errors = []
        for i, row in enumerate(reader):
            try:
                event = Event(
                    organization_id=org_id,
                    event_name=row.get("event_name", "csv_import"),
                    timestamp=datetime.fromisoformat(row["timestamp"]) if "timestamp" in row else datetime.now(timezone.utc),
                    properties={k: v for k, v in row.items() if k not in ("event_name", "timestamp", "numeric_value", "user_id")},
                    user_id_ext=row.get("user_id"),
                    numeric_value=float(row["numeric_value"]) if row.get("numeric_value") else None,
                )
                events.append(event)
            except Exception as e:
                errors.append({"row": i + 1, "error": str(e)})

        if events:
            self.db.add_all(events)
            await self.db.flush()

        logger.info("csv_ingested", org_id=org_id, count=len(events), errors=len(errors))
        return {
            "ingested": len(events),
            "errors": len(errors),
            "error_details": errors[:10],  # return first 10 errors
        }

    async def list_events(
        self, org_id: str, page: int = 1, page_size: int = 50,
        event_name: str = None, start_date: datetime = None, end_date: datetime = None,
    ) -> dict:
        """List events with pagination and filtering."""
        query = select(Event).where(Event.organization_id == org_id)

        if event_name:
            query = query.where(Event.event_name == event_name)
        if start_date:
            query = query.where(Event.timestamp >= start_date)
        if end_date:
            query = query.where(Event.timestamp <= end_date)

        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar()

        # Fetch page
        query = query.order_by(Event.timestamp.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)
        result = await self.db.execute(query)
        events = result.scalars().all()

        return {
            "events": [EventResponse.model_validate(e) for e in events],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    async def get_event_names(self, org_id: str) -> list[str]:
        """Get distinct event names for an organization."""
        result = await self.db.execute(
            select(Event.event_name)
            .where(Event.organization_id == org_id)
            .distinct()
        )
        return [row[0] for row in result.all()]

    # ── API Key Management ──────────────────────────────────────────

    async def create_api_key(
        self, org_id: str, req: APIKeyCreate, user_id: str
    ) -> APIKeyCreatedResponse:
        """Generate a new API key for the organization."""
        raw_key = generate_api_key()
        key_hash = hash_api_key(raw_key)

        api_key = APIKey(
            organization_id=org_id,
            name=req.name,
            key_hash=key_hash,
            key_prefix=raw_key[:10],
            created_by=user_id,
        )
        self.db.add(api_key)
        await self.db.flush()

        logger.info("api_key_created", org_id=org_id, key_name=req.name)
        return APIKeyCreatedResponse(
            id=api_key.id,
            name=api_key.name,
            key=raw_key,
            key_prefix=api_key.key_prefix,
            created_at=api_key.created_at,
        )

    async def list_api_keys(self, org_id: str) -> list[APIKeyResponse]:
        """List all API keys for an organization."""
        result = await self.db.execute(
            select(APIKey)
            .where(APIKey.organization_id == org_id)
            .order_by(APIKey.created_at.desc())
        )
        keys = result.scalars().all()
        return [APIKeyResponse.model_validate(k) for k in keys]

    async def revoke_api_key(self, org_id: str, key_id: str) -> None:
        """Revoke an API key."""
        result = await self.db.execute(
            select(APIKey).where(
                APIKey.id == key_id,
                APIKey.organization_id == org_id,
            )
        )
        key = result.scalar_one_or_none()
        if not key:
            raise ValueError("API key not found")
        key.is_active = False
        key.revoked_at = datetime.now(timezone.utc)
        await self.db.flush()
        logger.info("api_key_revoked", org_id=org_id, key_id=key_id)

    async def validate_api_key(self, raw_key: str) -> tuple[str, str]:
        """Validate an API key and return (org_id, key_id)."""
        key_hash = hash_api_key(raw_key)
        result = await self.db.execute(
            select(APIKey).where(
                APIKey.key_hash == key_hash,
                APIKey.is_active == True,
            )
        )
        api_key = result.scalar_one_or_none()
        if not api_key:
            raise ValueError("Invalid API key")

        api_key.last_used_at = datetime.now(timezone.utc)
        await self.db.flush()
        return api_key.organization_id, api_key.id

    # ── Data Sources ────────────────────────────────────────────────

    async def create_data_source(
        self, org_id: str, req: DataSourceCreate
    ) -> DataSourceResponse:
        ds = DataSource(
            organization_id=org_id,
            name=req.name,
            source_type=req.source_type,
            config=req.config,
        )
        self.db.add(ds)
        await self.db.flush()
        return DataSourceResponse.model_validate(ds)

    async def list_data_sources(self, org_id: str) -> list[DataSourceResponse]:
        result = await self.db.execute(
            select(DataSource).where(DataSource.organization_id == org_id)
        )
        return [DataSourceResponse.model_validate(ds) for ds in result.scalars().all()]

    # ── Stats ───────────────────────────────────────────────────────

    async def get_ingestion_stats(self, org_id: str) -> IngestionStatsResponse:
        """Get ingestion stats for an organization."""
        total = await self.db.execute(
            select(func.count(Event.id)).where(Event.organization_id == org_id)
        )
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        today = await self.db.execute(
            select(func.count(Event.id)).where(
                Event.organization_id == org_id,
                Event.timestamp >= today_start,
            )
        )
        unique_names = await self.db.execute(
            select(func.count(func.distinct(Event.event_name))).where(
                Event.organization_id == org_id
            )
        )
        ds_count = await self.db.execute(
            select(func.count(DataSource.id)).where(
                DataSource.organization_id == org_id
            )
        )

        return IngestionStatsResponse(
            total_events=total.scalar() or 0,
            events_today=today.scalar() or 0,
            unique_event_names=unique_names.scalar() or 0,
            data_sources=ds_count.scalar() or 0,
        )
