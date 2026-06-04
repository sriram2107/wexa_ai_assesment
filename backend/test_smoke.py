"""Quick smoke test for the Analytics Platform API."""
import httpx
import json

BASE = "http://localhost:8000/api"

def test():
    c = httpx.Client(base_url=BASE, timeout=10)
    
    # 1. Health check
    r = c.get("/health")
    assert r.status_code == 200
    print(f"✅ Health: {r.json()['status']}")
    
    # 2. Register new user
    r = c.post("/auth/register", json={
        "email": "test@example.com",
        "password": "testpassword123",
        "full_name": "Test User",
        "org_name": "Test Org"
    })
    assert r.status_code == 201, f"Register failed: {r.text}"
    tokens = r.json()
    print(f"✅ Register: got access + refresh tokens")
    
    # Set auth header
    c.headers["Authorization"] = f"Bearer {tokens['access_token']}"
    
    # 3. Get current user
    r = c.get("/auth/me")
    assert r.status_code == 200
    user = r.json()
    print(f"✅ User: {user['full_name']} ({user['role']})")
    
    # 4. Login with demo user
    r = c.post("/auth/login", json={
        "email": "demo@analytics.com",
        "password": "demo1234"
    })
    if r.status_code == 200:
        tokens = r.json()
        c.headers["Authorization"] = f"Bearer {tokens['access_token']}"
        print(f"✅ Login: demo user authenticated")
    else:
        print(f"⚠️ Demo login: {r.status_code} (no demo data in fresh db)")
    
    # 5. Ingest single event
    r = c.post("/events/ingest", json={
        "event_name": "test_event",
        "properties": {"source": "smoke_test", "page": "/test"},
        "numeric_value": 42.5
    })
    assert r.status_code == 201
    print(f"✅ Ingest single: event_id={r.json()['id'][:8]}...")
    
    # 6. Ingest batch
    r = c.post("/events/ingest/batch", json={
        "events": [
            {"event_name": "page_view", "properties": {"page": "/home"}},
            {"event_name": "button_click", "properties": {"button": "signup"}},
            {"event_name": "purchase", "numeric_value": 99.99, "properties": {"product": "Pro"}},
        ]
    })
    assert r.status_code == 201
    print(f"✅ Ingest batch: {r.json()['ingested']} events")
    
    # 7. List events
    r = c.get("/events/?page=1&page_size=5")
    assert r.status_code == 200
    print(f"✅ List events: {r.json()['total']} total, showing {len(r.json()['events'])}")
    
    # 8. Get event names
    r = c.get("/events/names")
    assert r.status_code == 200
    print(f"✅ Event names: {r.json()}")
    
    # 9. Get stats
    r = c.get("/events/stats")
    assert r.status_code == 200
    stats = r.json()
    print(f"✅ Stats: {stats['total_events']} total, {stats['events_today']} today")
    
    # 10. Create dashboard
    r = c.post("/dashboards/", json={
        "name": "Test Dashboard",
        "description": "Created by smoke test",
        "auto_refresh_seconds": 30
    })
    assert r.status_code == 201
    dash = r.json()
    print(f"✅ Dashboard created: {dash['id'][:8]}...")
    
    # 11. Add widget
    r = c.post(f"/dashboards/{dash['id']}/widgets", json={
        "title": "Test Events Count",
        "widget_type": "kpi",
        "event_name": "test_event",
        "aggregation": "count",
        "time_range": "7d",
        "grid_w": 3,
        "grid_h": 2
    })
    assert r.status_code == 201
    widget = r.json()
    print(f"✅ Widget added: {widget['widget_type']} - data={widget.get('data', {}).get('summary', {})}")
    
    # 12. Get dashboard with data
    r = c.get(f"/dashboards/{dash['id']}")
    assert r.status_code == 200
    detail = r.json()
    print(f"✅ Dashboard detail: {detail['widget_count']} widgets")
    
    # 13. Create alert rule
    r = c.post("/alerts/rules", json={
        "name": "High Event Count",
        "event_name": "test_event",
        "metric": "count",
        "condition": "gt",
        "threshold": 100,
        "window_minutes": 60
    })
    assert r.status_code == 201
    alert = r.json()
    print(f"✅ Alert rule: {alert['name']} ({alert['status']})")
    
    # 14. Evaluate alerts
    r = c.post("/alerts/evaluate")
    assert r.status_code == 200
    print(f"✅ Alert evaluation: {r.json()}")
    
    # 15. Create API key
    r = c.post("/api-keys/", json={"name": "Test Key"})
    assert r.status_code == 201
    key = r.json()
    print(f"✅ API Key: {key['key_prefix']}... (full key shown once)")
    
    # 16. List members
    r = c.get("/auth/members")
    assert r.status_code == 200
    print(f"✅ Members: {len(r.json())} member(s)")
    
    # 17. Invite member
    r = c.post("/auth/invite", json={"email": "new@example.com", "role": "analyst"})
    assert r.status_code == 200
    print(f"✅ Invitation sent to new@example.com")
    
    # 18. Frontend served
    r = httpx.get("http://localhost:8000/")
    assert r.status_code == 200
    assert "Analytics Platform" in r.text
    print(f"✅ Frontend: HTML served ({len(r.text)} bytes)")
    
    # 19. Swagger docs
    r = httpx.get("http://localhost:8000/api/docs")
    assert r.status_code == 200
    print(f"✅ Swagger docs: accessible")
    
    print("\n🎉 ALL TESTS PASSED! Platform is fully functional.")

if __name__ == "__main__":
    test()
