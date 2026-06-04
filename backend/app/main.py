"""
FastAPI application factory.
Configures CORS, exception handlers, lifespan events, and mounts all routers.
"""

import uuid
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.database import init_db, close_db
from app.routers import auth, ingestion, dashboards, alerts, websocket

# ── Structured Logging ──────────────────────────────────────────────

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(0),
)

logger = structlog.get_logger()


# ── Lifespan ────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup/shutdown lifecycle."""
    logger.info("starting_app", app_name=settings.APP_NAME, version=settings.APP_VERSION)
    await init_db()
    logger.info("database_initialized")

    # Seed demo data if database is empty
    await _seed_demo_data()

    yield

    await close_db()
    logger.info("app_shutdown")


# ── App Creation ────────────────────────────────────────────────────

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Real-Time Analytics & Reporting Platform API",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# ── CORS ────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Correlation ID Middleware ───────────────────────────────────────

@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    """Add correlation ID to every request for tracing."""
    correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(correlation_id=correlation_id)

    response = await call_next(request)
    response.headers["X-Correlation-ID"] = correlation_id
    return response


# ── Exception Handlers ──────────────────────────────────────────────

@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": str(exc)},
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error("unhandled_exception", error=str(exc), path=request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
    )


# ── Register Routers ───────────────────────────────────────────────

app.include_router(auth.router, prefix="/api")
app.include_router(ingestion.router, prefix="/api")
app.include_router(ingestion.keys_router, prefix="/api")
app.include_router(dashboards.router, prefix="/api")
app.include_router(alerts.router, prefix="/api")
app.include_router(websocket.router)


# ── Health Check ────────────────────────────────────────────────────

@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    from app.services.realtime_service import ws_manager
    return {
        "status": "healthy",
        "version": settings.APP_VERSION,
        "ws_connections": ws_manager.get_connection_count(),
    }


# ── Static Files & Frontend ─────────────────────────────────────────

import os
from pathlib import Path
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

static_dir = Path(__file__).parent.parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/")
async def serve_frontend():
    """Serve the SPA frontend."""
    html_path = static_dir / "index.html"
    return FileResponse(str(html_path))


# ── Demo Data Seed ──────────────────────────────────────────────────

async def _seed_demo_data():
    """Seed database with demo data if empty."""
    from app.core.database import async_session_factory
    from app.models.user import User, Organization, Membership
    from app.models.ingestion import Event, DataSource
    from app.core.security import hash_password
    from sqlalchemy import select, func
    import random
    from datetime import datetime, timedelta, timezone

    async with async_session_factory() as db:
        # Check if data exists
        result = await db.execute(select(func.count(User.id)))
        if result.scalar() > 0:
            return

        logger.info("seeding_demo_data")

        # Create demo user + org
        user = User(
            email="demo@analytics.com",
            full_name="Demo User",
            hashed_password=hash_password("demo1234"),
            is_active=True,
            is_verified=True,
        )
        db.add(user)
        await db.flush()

        org = Organization(name="Demo Organization", slug="demo-org")
        db.add(org)
        await db.flush()

        membership = Membership(user_id=user.id, organization_id=org.id, role="owner")
        db.add(membership)

        # Create data source
        ds = DataSource(
            organization_id=org.id,
            name="Website Tracker",
            source_type="api",
        )
        db.add(ds)
        await db.flush()

        # Seed events (past 30 days)
        event_types = [
            ("page_view", ["page", "source", "browser"]),
            ("button_click", ["button_id", "page", "element"]),
            ("purchase", ["product", "method", "category"]),
            ("signup", ["plan", "source", "country"]),
            ("error", ["type", "service", "severity"]),
            ("api_call", ["endpoint", "method", "status_code"]),
        ]

        pages = ["/home", "/pricing", "/docs", "/blog", "/about", "/contact", "/features"]
        sources = ["google", "direct", "twitter", "linkedin", "github", "referral"]
        browsers = ["Chrome", "Firefox", "Safari", "Edge"]
        products = ["Basic Plan", "Pro Plan", "Enterprise", "Add-on Pack"]
        methods = ["credit_card", "paypal", "stripe", "bank_transfer"]
        services = ["api-gateway", "auth-service", "data-processor", "worker", "frontend"]
        error_types = ["TypeError", "ValueError", "ConnectionError", "TimeoutError"]
        severities = ["low", "medium", "high", "critical"]
        countries = ["US", "UK", "DE", "FR", "IN", "JP", "BR", "AU"]
        plans = ["free", "basic", "pro", "enterprise"]

        now = datetime.now(timezone.utc)
        events = []

        for day_offset in range(30, 0, -1):
            day = now - timedelta(days=day_offset)
            # More events on weekdays
            daily_count = random.randint(40, 120) if day.weekday() < 5 else random.randint(15, 50)

            for _ in range(daily_count):
                event_type, prop_keys = random.choice(event_types)
                hour = random.randint(0, 23)
                minute = random.randint(0, 59)
                ts = day.replace(hour=hour, minute=minute, second=random.randint(0, 59))

                props = {}
                numeric = None

                if event_type == "page_view":
                    props = {"page": random.choice(pages), "source": random.choice(sources), "browser": random.choice(browsers)}
                elif event_type == "button_click":
                    props = {"button_id": f"btn_{random.randint(1,20)}", "page": random.choice(pages)}
                elif event_type == "purchase":
                    numeric = round(random.uniform(9.99, 499.99), 2)
                    props = {"product": random.choice(products), "method": random.choice(methods), "category": "subscription"}
                elif event_type == "signup":
                    props = {"plan": random.choice(plans), "source": random.choice(sources), "country": random.choice(countries)}
                elif event_type == "error":
                    props = {"type": random.choice(error_types), "service": random.choice(services), "severity": random.choice(severities)}
                elif event_type == "api_call":
                    numeric = round(random.uniform(10, 2000), 1)
                    props = {"endpoint": random.choice(["/api/users", "/api/data", "/api/events"]), "method": random.choice(["GET", "POST"]), "status_code": random.choice(["200", "201", "400", "500"])}

                event = Event(
                    organization_id=org.id,
                    data_source_id=ds.id,
                    event_name=event_type,
                    timestamp=ts,
                    properties=props,
                    user_id_ext=f"user_{random.randint(1, 100)}",
                    session_id=f"sess_{random.randint(1, 500)}",
                    numeric_value=numeric,
                )
                events.append(event)

        db.add_all(events)
        await db.commit()
        logger.info("demo_data_seeded", event_count=len(events))
