[README.md]
# Real-Time Analytics & Reporting Platform

A production-grade SaaS analytics platform built with **FastAPI**, **SQLAlchemy 2.0** (async), and a **JavaScript SPA** frontend with **Chart.js**.

## 🏗 Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Frontend (SPA)                     │
│   HTML/CSS/JS • Chart.js • WebSocket Client          │
├─────────────────────────────────────────────────────┤
│                   FastAPI Backend                    │
│                                                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  │
│  │  Routers  │→│ Services  │→│  Repositories/DB  │  │
│  └──────────┘  └──────────┘  └──────────────────┘  │
│                                                     │
│  • JWT Auth + Role-based Access Control             │
│  • WebSocket Manager (live dashboards/events)       │
│  • Correlation ID Middleware                        │
│  • Structured Logging (structlog)                   │
├─────────────────────────────────────────────────────┤
│  SQLite (dev) / PostgreSQL (prod)                   │
│  SQLAlchemy 2.0 Async + Alembic Migrations          │
└─────────────────────────────────────────────────────┘
```

### Clean Architecture (Layered Separation)

```
Routers (API endpoints)
  → Services (business logic)
    → Models (SQLAlchemy ORM)
      → Database (async sessions)
```

- **Dependency Injection** via FastAPI `Depends`
- **Organization-level data isolation** at the query layer
- **Role hierarchy**: Owner → Admin → Analyst → Viewer

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- pip

### 1. Install Dependencies

```bash
cd backend
pip install -r requirements.txt
```

### 2. Run the Server

```bash
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 3. Open the App

Navigate to **http://localhost:8000** in your browser.

### 4. Demo Login

```
Email:    demo@analytics.com
Password: demo1234
```

The app auto-seeds ~2,000 demo events across 6 event types over 30 days.

## 📊 Features

### ✅ Must Have (Implemented)

| Feature | Description |
|---------|-------------|
| **JWT Authentication** | Access tokens (30min) + refresh tokens (7 days) |
| **Multi-Tenancy** | Organization-scoped data isolation at query layer |
| **Role-Based Access** | Owner/Admin/Analyst/Viewer with permission guards |
| **Invite System** | Token-based email invitations with role assignment |
| **Event Ingestion (Single)** | POST /api/events/ingest |
| **Event Ingestion (Batch)** | POST /api/events/ingest/batch (up to 1000) |
| **CSV Upload** | POST /api/events/ingest/csv with validation |
| **API Key Auth** | Generate/revoke API keys for ingestion |
| **Pydantic Validation** | v2 models on all request/response schemas |
| **Custom Dashboards** | Create dashboards with template support |
| **Widget Types** | Line, Bar, Pie, KPI, Table charts |
| **Saved Queries** | Configurable aggregation, grouping, time ranges |
| **Dashboard Sharing** | Public read-only links via token |
| **Auto-Refresh** | Configurable intervals (30s, 1m, 5m) |
| **Dashboard Templates** | Web Analytics, Sales, DevOps presets |

### ✅ Should Have (Implemented)

| Feature | Description |
|---------|-------------|
| **Alert Rules** | Threshold-based (count/sum/avg with gt/lt/gte/lte) |
| **Alert Evaluation** | Manual trigger + background-ready (Celery Beat) |
| **Alert Muting** | Snooze alerts for configurable duration |
| **Alert History** | Full audit trail with triggered values |
| **WebSocket Live Dashboard** | Real-time dashboard updates on new events |
| **Live Event Stream** | Tail incoming events in real-time |
| **Real-time Alert Push** | Alert notifications via WebSocket |

## 🛠 Technical Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | FastAPI (Python 3.11+) |
| **Database** | SQLite (dev) / PostgreSQL (prod) via SQLAlchemy 2.0 async |
| **Auth** | JWT (python-jose) + bcrypt password hashing |
| **Validation** | Pydantic v2 |
| **Real-Time** | WebSockets (FastAPI/Starlette) |
| **Logging** | structlog (structured, with correlation IDs) |
| **Frontend** | Vanilla JS SPA + Chart.js |
| **Styling** | Custom CSS (dark glassmorphism theme) |

## 📁 Project Structure

```
backend/
├── app/
│   ├── main.py                 # FastAPI app factory, lifespan, middleware
│   ├── core/
│   │   ├── config.py           # Pydantic Settings (env vars)
│   │   ├── database.py         # Async SQLAlchemy engine + sessions
│   │   └── security.py         # JWT, bcrypt, API keys, role guards
│   ├── models/
│   │   ├── user.py             # User, Organization, Membership, Invitation
│   │   ├── ingestion.py        # Event, DataSource, APIKey
│   │   ├── dashboard.py        # Dashboard, Widget, SavedQuery
│   │   └── alert.py            # AlertRule, AlertHistory, NotificationChannel
│   ├── schemas/
│   │   ├── auth.py             # Auth/user request/response schemas
│   │   ├── ingestion.py        # Event/API key schemas
│   │   ├── dashboard.py        # Dashboard/widget/query schemas
│   │   └── alert.py            # Alert/notification schemas
│   ├── services/
│   │   ├── auth_service.py     # Registration, login, invites, members
│   │   ├── ingestion_service.py# Event processing, CSV, API keys
│   │   ├── dashboard_service.py# Dashboard CRUD, query execution engine
│   │   ├── alert_service.py    # Alert CRUD, evaluation engine
│   │   └── realtime_service.py # WebSocket connection manager
│   └── routers/
│       ├── auth.py             # /api/auth/*
│       ├── ingestion.py        # /api/events/*, /api/api-keys/*
│       ├── dashboards.py       # /api/dashboards/*
│       ├── alerts.py           # /api/alerts/*
│       └── websocket.py        # /ws/*
├── static/
│   ├── index.html              # SPA frontend
│   ├── styles.css              # Design system (dark theme)
│   └── app.js                  # Frontend application logic
├── requirements.txt
└── docker-compose.yml
```

## 🔑 API Endpoints

### Authentication
- `POST /api/auth/register` — Register + create org
- `POST /api/auth/login` — Login with email/password
- `POST /api/auth/refresh` — Refresh access token
- `GET  /api/auth/me` — Current user info
- `POST /api/auth/invite` — Invite team member (admin+)
- `POST /api/auth/accept-invite` — Accept invitation
- `GET  /api/auth/members` — List org members
- `PATCH /api/auth/members/{id}/role` — Update role (admin+)

### Data Ingestion
- `POST /api/events/ingest` — Single event (JWT auth)
- `POST /api/events/ingest/batch` — Batch events (up to 1000)
- `POST /api/events/ingest/csv` — CSV file upload
- `POST /api/events/ingest/api-key` — Single event (API key auth)
- `GET  /api/events/` — List events (paginated, filterable)
- `GET  /api/events/names` — Distinct event names
- `GET  /api/events/stats` — Ingestion statistics

### API Keys
- `POST /api/api-keys/` — Generate new key (analyst+)
- `GET  /api/api-keys/` — List keys
- `DELETE /api/api-keys/{id}` — Revoke key

### Dashboards
- `POST /api/dashboards/` — Create dashboard
- `GET  /api/dashboards/` — List dashboards
- `GET  /api/dashboards/{id}` — Get with widget data
- `PATCH /api/dashboards/{id}` — Update settings
- `DELETE /api/dashboards/{id}` — Delete (admin+)
- `GET  /api/dashboards/public/{token}` — Public view

### Widgets
- `POST /api/dashboards/{id}/widgets` — Add widget
- `PATCH /api/dashboards/{id}/widgets/{wid}` — Update
- `DELETE /api/dashboards/{id}/widgets/{wid}` — Remove

### Alerts
- `POST /api/alerts/rules` — Create alert rule
- `GET  /api/alerts/rules` — List rules
- `PATCH /api/alerts/rules/{id}` — Update rule
- `DELETE /api/alerts/rules/{id}` — Delete rule
- `POST /api/alerts/rules/{id}/mute` — Mute alert
- `GET  /api/alerts/history` — Alert history
- `POST /api/alerts/evaluate` — Manual evaluation trigger

### WebSocket
- `WS /ws/dashboard?token=<jwt>` — Live dashboard updates
- `WS /ws/events?token=<jwt>` — Live event stream
- `WS /ws/alerts?token=<jwt>` — Alert notifications

### Health
- `GET /api/health` — Health check
- `GET /api/docs` — Swagger UI
- `GET /api/redoc` — ReDoc

## 🔧 Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | `super-secret-key-...` | JWT signing key |
| `DATABASE_URL` | `sqlite+aiosqlite:///./analytics.db` | Database connection |
| `CORS_ORIGINS` | `["http://localhost:3000"]` | Allowed origins |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | JWT access token TTL |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` | Refresh token TTL |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis (for Celery) |

## 📐 Design Decisions

1. **SQLite for dev**: Zero-dependency setup. Switch to PostgreSQL by changing `DATABASE_URL`
2. **Async throughout**: `async/await` on all endpoints, DB queries (SQLAlchemy 2.0 async)
3. **bcrypt direct**: Used bcrypt library directly instead of passlib to avoid compatibility issues
4. **SPA frontend**: Served by FastAPI's static files — single deployment unit
5. **WebSocket auth**: JWT token passed as query parameter for WebSocket connections
6. **Time-series indexing**: Events table indexed on `(org_id, event_name, timestamp)` for efficient aggregation queries
