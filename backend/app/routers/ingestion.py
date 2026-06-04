"""
Event ingestion & API key management endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, Header, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.core.database import get_db
from app.core.security import get_current_user_with_org, require_analyst
from app.schemas.ingestion import (
    EventCreate,
    BatchEventsCreate,
    EventResponse,
    EventsListResponse,
    APIKeyCreate,
    APIKeyCreatedResponse,
    APIKeyResponse,
    DataSourceCreate,
    DataSourceResponse,
    IngestionStatsResponse,
)
from app.services.ingestion_service import IngestionService
from app.services.realtime_service import ws_manager

router = APIRouter(prefix="/events", tags=["Data Ingestion"])
keys_router = APIRouter(prefix="/api-keys", tags=["API Keys"])


# ── Event Ingestion ─────────────────────────────────────────────────

@router.post("/ingest", response_model=EventResponse, status_code=status.HTTP_201_CREATED)
async def ingest_event(
    event: EventCreate,
    user=Depends(get_current_user_with_org),
    db: AsyncSession = Depends(get_db),
):
    """Ingest a single event (authenticated user)."""
    service = IngestionService(db)
    org_id = user.current_membership.organization_id
    result = await service.ingest_single_event(org_id, event)

    # Broadcast to live event stream
    await ws_manager.broadcast_event(org_id, result.model_dump(mode="json"))
    return result


@router.post("/ingest/batch", status_code=status.HTTP_201_CREATED)
async def ingest_batch(
    batch: BatchEventsCreate,
    user=Depends(get_current_user_with_org),
    db: AsyncSession = Depends(get_db),
):
    """Ingest a batch of events (up to 1000)."""
    service = IngestionService(db)
    org_id = user.current_membership.organization_id
    result = await service.ingest_batch_events(org_id, batch)

    # Broadcast dashboard update
    await ws_manager.broadcast_dashboard_update(org_id, "all")
    return result


@router.post("/ingest/csv", status_code=status.HTTP_201_CREATED)
async def ingest_csv(
    file: UploadFile = File(...),
    user=Depends(get_current_user_with_org),
    db: AsyncSession = Depends(get_db),
):
    """Upload a CSV file for event ingestion."""
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are supported")

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:  # 10MB limit
        raise HTTPException(status_code=400, detail="File too large (max 10MB)")

    service = IngestionService(db)
    org_id = user.current_membership.organization_id
    return await service.ingest_csv(org_id, content, file.filename)


@router.post("/ingest/api-key", response_model=EventResponse, status_code=status.HTTP_201_CREATED)
async def ingest_with_api_key(
    event: EventCreate,
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: AsyncSession = Depends(get_db),
):
    """Ingest a single event using API key authentication."""
    service = IngestionService(db)
    try:
        org_id, key_id = await service.validate_api_key(x_api_key)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")

    result = await service.ingest_single_event(org_id, event)
    await ws_manager.broadcast_event(org_id, result.model_dump(mode="json"))
    return result


@router.get("/", response_model=EventsListResponse)
async def list_events(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    event_name: Optional[str] = None,
    user=Depends(get_current_user_with_org),
    db: AsyncSession = Depends(get_db),
):
    """List events with pagination and filtering."""
    service = IngestionService(db)
    org_id = user.current_membership.organization_id
    result = await service.list_events(org_id, page, page_size, event_name)
    return EventsListResponse(**result)


@router.get("/names", response_model=list[str])
async def get_event_names(
    user=Depends(get_current_user_with_org),
    db: AsyncSession = Depends(get_db),
):
    """Get all distinct event names for the organization."""
    service = IngestionService(db)
    return await service.get_event_names(user.current_membership.organization_id)


@router.get("/stats", response_model=IngestionStatsResponse)
async def get_stats(
    user=Depends(get_current_user_with_org),
    db: AsyncSession = Depends(get_db),
):
    """Get ingestion statistics for the organization."""
    service = IngestionService(db)
    return await service.get_ingestion_stats(user.current_membership.organization_id)


# ── API Keys ────────────────────────────────────────────────────────

@keys_router.post("/", response_model=APIKeyCreatedResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    req: APIKeyCreate,
    user=Depends(require_analyst),
    db: AsyncSession = Depends(get_db),
):
    """Generate a new API key (analyst+ only). Key is shown only once."""
    service = IngestionService(db)
    return await service.create_api_key(
        user.current_membership.organization_id,
        req,
        user.id,
    )


@keys_router.get("/", response_model=list[APIKeyResponse])
async def list_api_keys(
    user=Depends(get_current_user_with_org),
    db: AsyncSession = Depends(get_db),
):
    """List all API keys for the organization."""
    service = IngestionService(db)
    return await service.list_api_keys(user.current_membership.organization_id)


@keys_router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(
    key_id: str,
    user=Depends(require_analyst),
    db: AsyncSession = Depends(get_db),
):
    """Revoke an API key."""
    try:
        service = IngestionService(db)
        await service.revoke_api_key(user.current_membership.organization_id, key_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
