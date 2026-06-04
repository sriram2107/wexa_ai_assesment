/* ═══════════════════════════════════════════════════════════════════
   Analytics Platform — Client Application
   State management, API calls, WebSocket, Chart rendering
   ═══════════════════════════════════════════════════════════════════ */

let API_BASE;
let wsBase;

const hostname = window.location.hostname;
if (hostname === 'localhost' || hostname === '127.0.0.1') {
    API_BASE = '/api';
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    wsBase = `${wsProtocol}//${window.location.host}/ws`;
} else {
    // Production Railway URL. (We will update this if different after provisioning)
    const railwayHost = 'wexa-ai-assesment-production.up.railway.app';
    API_BASE = `https://${railwayHost}/api`;
    wsBase = `wss://${railwayHost}/ws`;
}

// ── State ────────────────────────────────────────────────────────────

const state = {
    token: localStorage.getItem('access_token'),
    refreshToken: localStorage.getItem('refresh_token'),
    user: null,
    currentPage: 'overview',
    dashboards: [],
    currentDashboard: null,
    alerts: [],
    eventStream: [],
    streamPaused: false,
    ws: null,
    wsEvents: null,
    wsAlerts: null,
    charts: {},
    autoRefreshInterval: null,
};

// ── API Client ───────────────────────────────────────────────────────

async function api(path, options = {}) {
    const headers = { 'Content-Type': 'application/json', ...options.headers };
    if (state.token) {
        headers['Authorization'] = `Bearer ${state.token}`;
    }

    const resp = await fetch(`${API_BASE}${path}`, {
        ...options,
        headers,
    });

    if (resp.status === 401 && state.refreshToken) {
        const refreshed = await refreshAccessToken();
        if (refreshed) {
            headers['Authorization'] = `Bearer ${state.token}`;
            const retry = await fetch(`${API_BASE}${path}`, { ...options, headers });
            if (!retry.ok) throw new Error(await retry.text());
            return retry.status === 204 ? null : retry.json();
        }
    }

    if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: 'Request failed' }));
        throw new Error(err.detail || JSON.stringify(err));
    }

    return resp.status === 204 ? null : resp.json();
}

async function refreshAccessToken() {
    try {
        const resp = await fetch(`${API_BASE}/auth/refresh`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ refresh_token: state.refreshToken }),
        });
        if (!resp.ok) return false;
        const data = await resp.json();
        setTokens(data.access_token, data.refresh_token);
        return true;
    } catch {
        logout();
        return false;
    }
}

function setTokens(access, refresh) {
    state.token = access;
    state.refreshToken = refresh;
    localStorage.setItem('access_token', access);
    localStorage.setItem('refresh_token', refresh);
}

function clearTokens() {
    state.token = null;
    state.refreshToken = null;
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
}

// ── Toast Notifications ──────────────────────────────────────────────

function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(20px)';
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

// ── Auth ──────────────────────────────────────────────────────────────

function initAuth() {
    // Tab switching
    document.querySelectorAll('.auth-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.auth-tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.auth-form').forEach(f => f.classList.remove('active'));
            tab.classList.add('active');
            document.getElementById(`${tab.dataset.tab}-form`).classList.add('active');
        });
    });

    // Login
    document.getElementById('login-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const btn = e.target.querySelector('button');
        btn.disabled = true;
        try {
            const data = await api('/auth/login', {
                method: 'POST',
                body: JSON.stringify({
                    email: document.getElementById('login-email').value,
                    password: document.getElementById('login-password').value,
                }),
            });
            setTokens(data.access_token, data.refresh_token);
            await enterApp();
        } catch (err) {
            showAuthError(err.message);
        } finally {
            btn.disabled = false;
        }
    });

    // Register
    document.getElementById('register-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const btn = e.target.querySelector('button');
        btn.disabled = true;
        try {
            const data = await api('/auth/register', {
                method: 'POST',
                body: JSON.stringify({
                    email: document.getElementById('reg-email').value,
                    password: document.getElementById('reg-password').value,
                    full_name: document.getElementById('reg-name').value,
                    org_name: document.getElementById('reg-org').value,
                }),
            });
            setTokens(data.access_token, data.refresh_token);
            await enterApp();
        } catch (err) {
            showAuthError(err.message);
        } finally {
            btn.disabled = false;
        }
    });
}

function showAuthError(message) {
    const el = document.getElementById('auth-error');
    el.textContent = message;
    el.classList.remove('hidden');
    setTimeout(() => el.classList.add('hidden'), 5000);
}

function logout() {
    clearTokens();
    state.user = null;
    disconnectWebSockets();
    document.getElementById('auth-screen').classList.add('active');
    document.getElementById('main-screen').classList.remove('active');
}

async function enterApp() {
    document.getElementById('auth-screen').classList.remove('active');
    document.getElementById('main-screen').classList.add('active');

    try {
        state.user = await api('/auth/me');
        updateUserUI();
        connectWebSockets();
        navigateTo('overview');
    } catch (err) {
        showToast('Failed to load user info', 'error');
        logout();
    }
}

function updateUserUI() {
    if (!state.user) return;
    document.getElementById('user-name').textContent = state.user.full_name;
    document.getElementById('user-role').textContent = state.user.role || 'owner';
    document.getElementById('user-avatar').textContent = state.user.full_name.charAt(0).toUpperCase();
}

// ── Navigation ───────────────────────────────────────────────────────

function initNavigation() {
    document.querySelectorAll('.nav-item').forEach(item => {
        item.addEventListener('click', () => navigateTo(item.dataset.page));
    });

    document.getElementById('logout-btn').addEventListener('click', logout);
    document.getElementById('sidebar-toggle').addEventListener('click', () => {
        document.getElementById('sidebar').classList.toggle('open');
    });
}

async function navigateTo(page) {
    state.currentPage = page;

    // Update nav
    document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
    document.querySelector(`.nav-item[data-page="${page}"]`)?.classList.add('active');

    // Update pages
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    document.getElementById(`page-${page}`)?.classList.add('active');

    // Update title
    const titles = { overview: 'Overview', dashboards: 'Dashboards', events: 'Live Events', alerts: 'Alerts', settings: 'Settings' };
    document.getElementById('page-title').textContent = titles[page] || page;

    // Load page data
    try {
        switch (page) {
            case 'overview': await loadOverview(); break;
            case 'dashboards': await loadDashboards(); break;
            case 'events': await loadEventNames(); break;
            case 'alerts': await loadAlerts(); break;
            case 'settings': await loadSettings(); break;
        }
    } catch (err) {
        showToast(`Error loading ${page}: ${err.message}`, 'error');
    }
}

// ── Overview Page ────────────────────────────────────────────────────

async function loadOverview() {
    const [stats, events] = await Promise.all([
        api('/events/stats'),
        api('/events/?page=1&page_size=20'),
    ]);

    // Render KPIs
    renderKPIs(stats);

    // Render recent events table
    renderEventsTable(events.events);

    // Load charts
    await loadOverviewCharts();
}

function renderKPIs(stats) {
    const grid = document.getElementById('kpi-grid');
    grid.innerHTML = `
        <div class="kpi-card">
            <div class="kpi-label">Total Events</div>
            <div class="kpi-value">${formatNumber(stats.total_events)}</div>
            <div class="kpi-change positive">All time</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-label">Today's Events</div>
            <div class="kpi-value">${formatNumber(stats.events_today)}</div>
            <div class="kpi-change positive">Today</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-label">Event Types</div>
            <div class="kpi-value">${stats.unique_event_names}</div>
            <div class="kpi-change">Unique types</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-label">Data Sources</div>
            <div class="kpi-value">${stats.data_sources}</div>
            <div class="kpi-change">Active</div>
        </div>
    `;
}

async function loadOverviewCharts() {
    const timeRange = document.getElementById('overview-time-range').value;

    // Get event names for breakdown
    const names = await api('/events/names');

    // Destroy existing charts
    Object.values(state.charts).forEach(c => c.destroy?.());
    state.charts = {};

    // Line chart — fetch events for main type
    const mainEvent = names[0] || 'page_view';
    try {
        // We'll create a saved query on the fly
        const queryResp = await api('/dashboards/queries', {
            method: 'POST',
            body: JSON.stringify({
                name: 'Overview Line',
                event_name: mainEvent,
                aggregation: 'count',
                time_range: timeRange,
                time_bucket: timeRange === '24h' ? '1h' : timeRange === '7d' ? '6h' : '1d',
            }),
        });

        const lineData = await api(`/dashboards/queries/${queryResp.id}/execute`);

        const lineCtx = document.getElementById('events-line-chart').getContext('2d');
        state.charts.line = new Chart(lineCtx, {
            type: 'line',
            data: {
                labels: lineData.labels.map(l => l.split(' ')[0]),
                datasets: [{
                    label: mainEvent,
                    data: lineData.datasets[0]?.data || [],
                    borderColor: '#6366f1',
                    backgroundColor: 'rgba(99, 102, 241, 0.1)',
                    fill: true,
                    tension: 0.4,
                    pointRadius: 2,
                    pointHoverRadius: 5,
                    borderWidth: 2,
                }],
            },
            options: getChartOptions('Events'),
        });
    } catch (err) {
        console.warn('Line chart error:', err);
    }

    // Pie chart — events by type
    try {
        const typeCounts = {};
        for (const name of names.slice(0, 6)) {
            const events = await api(`/events/?event_name=${encodeURIComponent(name)}&page_size=1`);
            typeCounts[name] = events.total;
        }

        const pieCtx = document.getElementById('events-pie-chart').getContext('2d');
        const pieColors = ['#6366f1', '#8b5cf6', '#ec4899', '#f59e0b', '#10b981', '#3b82f6'];
        state.charts.pie = new Chart(pieCtx, {
            type: 'doughnut',
            data: {
                labels: Object.keys(typeCounts),
                datasets: [{
                    data: Object.values(typeCounts),
                    backgroundColor: pieColors,
                    borderWidth: 0,
                    hoverOffset: 8,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'right',
                        labels: { color: '#a0a0c0', font: { family: 'Inter', size: 11 }, padding: 12, usePointStyle: true },
                    },
                },
                cutout: '65%',
            },
        });
    } catch (err) {
        console.warn('Pie chart error:', err);
    }
}

function renderEventsTable(events) {
    const container = document.getElementById('recent-events-table');
    if (!events.length) {
        container.innerHTML = '<p style="padding:1rem;color:var(--text-muted)">No events yet</p>';
        return;
    }
    container.innerHTML = `
        <table>
            <thead>
                <tr>
                    <th>Time</th>
                    <th>Event</th>
                    <th>User</th>
                    <th>Properties</th>
                    <th>Value</th>
                </tr>
            </thead>
            <tbody>
                ${events.map(e => `
                    <tr>
                        <td>${formatTime(e.timestamp)}</td>
                        <td><span class="event-badge ${e.event_name}">${e.event_name}</span></td>
                        <td>${e.user_id_ext || '—'}</td>
                        <td style="max-width:300px;overflow:hidden;text-overflow:ellipsis">${JSON.stringify(e.properties).slice(0, 60)}</td>
                        <td>${e.numeric_value != null ? e.numeric_value : '—'}</td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
    `;
}

// ── Dashboards Page ──────────────────────────────────────────────────

async function loadDashboards() {
    document.getElementById('dashboards-list').classList.remove('hidden');
    document.getElementById('dashboard-detail').classList.add('hidden');

    state.dashboards = await api('/dashboards/');
    renderDashboardsList();
}

function renderDashboardsList() {
    const container = document.getElementById('dashboards-list');
    if (!state.dashboards.length) {
        container.innerHTML = `
            <div class="dashboard-card" style="text-align:center;color:var(--text-muted);cursor:default">
                <h4>No dashboards yet</h4>
                <p>Create your first dashboard to start visualizing data</p>
            </div>
        `;
        return;
    }

    container.innerHTML = state.dashboards.map(d => `
        <div class="dashboard-card" onclick="openDashboard('${d.id}')">
            <h4>${escapeHtml(d.name)}</h4>
            <p>${escapeHtml(d.description || 'No description')}</p>
            <div class="dashboard-meta">
                <span>📊 ${d.widget_count} widgets</span>
                <span>${d.auto_refresh_seconds > 0 ? `⚡ ${d.auto_refresh_seconds}s refresh` : ''}</span>
                <span>${d.is_public ? '🌐 Public' : '🔒 Private'}</span>
            </div>
        </div>
    `).join('');
}

async function openDashboard(id) {
    document.getElementById('dashboards-list').classList.add('hidden');
    document.getElementById('dashboard-detail').classList.remove('hidden');

    try {
        state.currentDashboard = await api(`/dashboards/${id}`);
        document.getElementById('dashboard-detail-title').textContent = state.currentDashboard.name;
        renderWidgets(state.currentDashboard.widgets);

        // Auto-refresh
        if (state.autoRefreshInterval) clearInterval(state.autoRefreshInterval);
        if (state.currentDashboard.auto_refresh_seconds > 0) {
            state.autoRefreshInterval = setInterval(async () => {
                state.currentDashboard = await api(`/dashboards/${id}`);
                renderWidgets(state.currentDashboard.widgets);
            }, state.currentDashboard.auto_refresh_seconds * 1000);
        }
    } catch (err) {
        showToast('Failed to load dashboard', 'error');
    }
}

function renderWidgets(widgets) {
    const grid = document.getElementById('widgets-grid');

    // Destroy existing widget charts
    Object.keys(state.charts).forEach(k => {
        if (k.startsWith('widget-')) {
            state.charts[k]?.destroy?.();
            delete state.charts[k];
        }
    });

    if (!widgets.length) {
        grid.innerHTML = '<p style="padding:2rem;color:var(--text-muted);grid-column:1/-1;text-align:center">No widgets. Click "Add Widget" to get started.</p>';
        return;
    }

    grid.innerHTML = widgets.map(w => {
        const colSpan = `grid-column: span ${Math.min(w.grid_w, 12)}`;
        const rowSpan = `grid-row: span ${Math.min(w.grid_h, 6)}`;
        return `
            <div class="widget-card" style="${colSpan};${rowSpan};min-height:${w.grid_h * 60}px" data-widget-id="${w.id}">
                <div class="widget-header">
                    <h4>${escapeHtml(w.title)}</h4>
                    <button class="btn-icon" onclick="deleteWidget('${w.id}')" title="Remove">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                    </button>
                </div>
                <div class="widget-body" id="widget-body-${w.id}">
                    ${w.widget_type === 'kpi'
                        ? `<div class="widget-kpi-value">${formatNumber(w.data?.summary?.total ?? 0)}</div>`
                        : `<canvas id="widget-chart-${w.id}"></canvas>`
                    }
                </div>
            </div>
        `;
    }).join('');

    // Render charts after DOM update
    requestAnimationFrame(() => {
        widgets.forEach(w => {
            if (w.widget_type !== 'kpi' && w.data) {
                renderWidgetChart(w);
            }
        });
    });
}

function renderWidgetChart(widget) {
    const canvas = document.getElementById(`widget-chart-${widget.id}`);
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    const colors = ['#6366f1', '#8b5cf6', '#ec4899', '#f59e0b', '#10b981', '#3b82f6'];
    const data = widget.data;

    let config;
    switch (widget.widget_type) {
        case 'line':
            config = {
                type: 'line',
                data: {
                    labels: data.labels.map(l => l.split(' ')[0]),
                    datasets: data.datasets.map((ds, i) => ({
                        label: ds.label,
                        data: ds.data,
                        borderColor: colors[i % colors.length],
                        backgroundColor: colors[i % colors.length] + '20',
                        fill: true,
                        tension: 0.4,
                        pointRadius: 1,
                        borderWidth: 2,
                    })),
                },
                options: getChartOptions(),
            };
            break;

        case 'bar':
            config = {
                type: 'bar',
                data: {
                    labels: data.labels,
                    datasets: data.datasets.map((ds, i) => ({
                        label: ds.label,
                        data: ds.data,
                        backgroundColor: colors.map(c => c + '80'),
                        borderColor: colors,
                        borderWidth: 1,
                        borderRadius: 4,
                    })),
                },
                options: getChartOptions(),
            };
            break;

        case 'pie':
            config = {
                type: 'doughnut',
                data: {
                    labels: data.labels,
                    datasets: [{
                        data: data.datasets[0]?.data || [],
                        backgroundColor: colors,
                        borderWidth: 0,
                    }],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            position: 'bottom',
                            labels: { color: '#a0a0c0', font: { family: 'Inter', size: 10 }, padding: 8, usePointStyle: true },
                        },
                    },
                    cutout: '60%',
                },
            };
            break;

        case 'table':
            // Render as table instead of chart
            const body = document.getElementById(`widget-body-${widget.id}`);
            body.innerHTML = `<table><thead><tr><th>Label</th><th>Value</th></tr></thead><tbody>
                ${data.labels.map((l, i) => `<tr><td>${l}</td><td>${data.datasets[0]?.data[i] || 0}</td></tr>`).join('')}
            </tbody></table>`;
            return;

        default:
            return;
    }

    state.charts[`widget-${widget.id}`] = new Chart(ctx, config);
}

function getChartOptions(yLabel = '') {
    return {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { intersect: false, mode: 'index' },
        plugins: {
            legend: {
                display: false,
            },
            tooltip: {
                backgroundColor: 'rgba(17, 17, 40, 0.95)',
                titleFont: { family: 'Inter' },
                bodyFont: { family: 'Inter' },
                borderColor: 'rgba(255,255,255,0.1)',
                borderWidth: 1,
                padding: 10,
                cornerRadius: 8,
            },
        },
        scales: {
            x: {
                grid: { color: 'rgba(255,255,255,0.04)' },
                ticks: { color: '#6a6a8e', font: { family: 'Inter', size: 10 }, maxTicksLimit: 8 },
            },
            y: {
                grid: { color: 'rgba(255,255,255,0.04)' },
                ticks: { color: '#6a6a8e', font: { family: 'Inter', size: 10 } },
                title: yLabel ? { display: true, text: yLabel, color: '#6a6a8e' } : undefined,
            },
        },
    };
}

// ── Events Page ──────────────────────────────────────────────────────

async function loadEventNames() {
    const names = await api('/events/names');
    const select = document.getElementById('event-name-filter');
    select.innerHTML = '<option value="">All Events</option>' +
        names.map(n => `<option value="${n}">${n}</option>`).join('');

    // Load initial events
    await loadEventStream();
}

async function loadEventStream() {
    const filter = document.getElementById('event-name-filter').value;
    const url = filter ? `/events/?page_size=50&event_name=${encodeURIComponent(filter)}` : '/events/?page_size=50';
    const data = await api(url);

    state.eventStream = data.events;
    renderEventStream();
}

function renderEventStream() {
    const container = document.getElementById('event-stream');
    container.innerHTML = state.eventStream.map(e => `
        <div class="event-stream-item">
            <span class="event-stream-time">${formatTime(e.timestamp)}</span>
            <span class="event-badge ${e.event_name}">${e.event_name}</span>
            <span class="event-stream-props">${JSON.stringify(e.properties)}</span>
            ${e.numeric_value != null ? `<span style="color:var(--success);font-weight:600">$${e.numeric_value}</span>` : ''}
        </div>
    `).join('');
}

// ── Alerts Page ──────────────────────────────────────────────────────

async function loadAlerts() {
    const [rules, history] = await Promise.all([
        api('/alerts/rules'),
        api('/alerts/history?limit=20'),
    ]);

    state.alerts = rules;
    renderAlertRules(rules);
    renderAlertHistory(history);
}

function renderAlertRules(rules) {
    const container = document.getElementById('alerts-list');
    if (!rules.length) {
        container.innerHTML = '<p style="padding:1rem;color:var(--text-muted)">No alert rules configured</p>';
        return;
    }

    container.innerHTML = rules.map(r => `
        <div class="alert-card">
            <div class="alert-info">
                <h4>${escapeHtml(r.name)}</h4>
                <p>${r.metric} of "${r.event_name}" ${r.condition} ${r.threshold} (${r.window_minutes}min window)</p>
            </div>
            <span class="alert-status ${r.status}">${r.status}</span>
            <div class="alert-actions">
                <button class="btn btn-sm btn-ghost" onclick="muteAlert('${r.id}')">Mute</button>
                <button class="btn btn-sm btn-danger" onclick="deleteAlert('${r.id}')">Delete</button>
            </div>
        </div>
    `).join('');
}

function renderAlertHistory(history) {
    const container = document.getElementById('alert-history-table');
    if (!history.length) {
        container.innerHTML = '<p style="padding:1rem;color:var(--text-muted)">No alert history</p>';
        return;
    }

    container.innerHTML = `
        <table>
            <thead>
                <tr><th>Time</th><th>Status</th><th>Value</th><th>Message</th></tr>
            </thead>
            <tbody>
                ${history.map(h => `
                    <tr>
                        <td>${formatTime(h.created_at)}</td>
                        <td><span class="alert-status ${h.status}">${h.status}</span></td>
                        <td>${h.triggered_value ?? '—'}</td>
                        <td style="max-width:400px;overflow:hidden;text-overflow:ellipsis">${h.message || '—'}</td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
    `;
}

async function muteAlert(id) {
    try {
        await api(`/alerts/rules/${id}/mute`, {
            method: 'POST',
            body: JSON.stringify({ mute_minutes: 60 }),
        });
        showToast('Alert muted for 1 hour', 'success');
        await loadAlerts();
    } catch (err) {
        showToast(err.message, 'error');
    }
}

async function deleteAlert(id) {
    if (!confirm('Delete this alert rule?')) return;
    try {
        await api(`/alerts/rules/${id}`, { method: 'DELETE' });
        showToast('Alert deleted', 'success');
        await loadAlerts();
    } catch (err) {
        showToast(err.message, 'error');
    }
}

// ── Settings Page ────────────────────────────────────────────────────

async function loadSettings() {
    const [members, keys] = await Promise.all([
        api('/auth/members'),
        api('/api-keys/'),
    ]);

    renderOrgInfo();
    renderMembers(members);
    renderAPIKeys(keys);
}

function renderOrgInfo() {
    const el = document.getElementById('org-info');
    el.innerHTML = `
        <p><strong>Organization:</strong> ${state.user?.organization_name || 'N/A'}</p>
        <p><strong>Your Role:</strong> <span class="role-badge">${state.user?.role || 'N/A'}</span></p>
    `;
}

function renderMembers(members) {
    const container = document.getElementById('members-list');
    container.innerHTML = members.map(m => `
        <div class="member-item">
            <div class="member-info">
                <div class="user-avatar">${m.full_name.charAt(0)}</div>
                <div>
                    <div class="member-name">${escapeHtml(m.full_name)}</div>
                    <div class="member-email">${escapeHtml(m.email)}</div>
                </div>
            </div>
            <span class="role-badge">${m.role}</span>
        </div>
    `).join('');
}

function renderAPIKeys(keys) {
    const container = document.getElementById('api-keys-list');
    if (!keys.length) {
        container.innerHTML = '<p style="padding:1rem;color:var(--text-muted)">No API keys</p>';
        return;
    }
    container.innerHTML = keys.map(k => `
        <div class="api-key-item">
            <div>
                <div class="api-key-name">${escapeHtml(k.name)}</div>
                <div class="api-key-prefix">${k.key_prefix}•••••••</div>
            </div>
            <div style="display:flex;align-items:center;gap:0.75rem">
                <span class="alert-status ${k.is_active ? 'active' : 'muted'}">${k.is_active ? 'Active' : 'Revoked'}</span>
                ${k.is_active ? `<button class="btn btn-sm btn-danger" onclick="revokeKey('${k.id}')">Revoke</button>` : ''}
            </div>
        </div>
    `).join('');
}

async function revokeKey(id) {
    if (!confirm('Revoke this API key?')) return;
    try {
        await api(`/api-keys/${id}`, { method: 'DELETE' });
        showToast('API key revoked', 'success');
        await loadSettings();
    } catch (err) {
        showToast(err.message, 'error');
    }
}

// ── Modals ───────────────────────────────────────────────────────────

function showModal(title, content) {
    document.getElementById('modal-title').textContent = title;
    document.getElementById('modal-body').innerHTML = content;
    document.getElementById('modal-overlay').classList.remove('hidden');
}

function closeModal() {
    document.getElementById('modal-overlay').classList.add('hidden');
}

function initModals() {
    document.getElementById('modal-close').addEventListener('click', closeModal);
    document.getElementById('modal-overlay').addEventListener('click', (e) => {
        if (e.target === e.currentTarget) closeModal();
    });

    // Create Dashboard
    document.getElementById('create-dashboard-btn').addEventListener('click', () => {
        showModal('Create Dashboard', `
            <form id="create-dashboard-form">
                <div class="form-group">
                    <label>Name</label>
                    <input type="text" id="new-dash-name" required placeholder="My Dashboard">
                </div>
                <div class="form-group">
                    <label>Description</label>
                    <textarea id="new-dash-desc" rows="2" placeholder="Optional description"></textarea>
                </div>
                <div class="form-group">
                    <label>Template</label>
                    <select id="new-dash-template">
                        <option value="">Blank</option>
                        <option value="web_analytics">Web Analytics</option>
                        <option value="sales">Sales</option>
                        <option value="devops">DevOps</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>Auto Refresh (seconds, 0 = off)</label>
                    <input type="number" id="new-dash-refresh" value="0" min="0">
                </div>
                <button type="submit" class="btn btn-primary btn-full">Create Dashboard</button>
            </form>
        `);
        document.getElementById('create-dashboard-form').addEventListener('submit', async (e) => {
            e.preventDefault();
            try {
                await api('/dashboards/', {
                    method: 'POST',
                    body: JSON.stringify({
                        name: document.getElementById('new-dash-name').value,
                        description: document.getElementById('new-dash-desc').value,
                        template_type: document.getElementById('new-dash-template').value || null,
                        auto_refresh_seconds: parseInt(document.getElementById('new-dash-refresh').value) || 0,
                    }),
                });
                closeModal();
                showToast('Dashboard created!', 'success');
                await loadDashboards();
            } catch (err) {
                showToast(err.message, 'error');
            }
        });
    });

    // Add Widget
    document.getElementById('add-widget-btn').addEventListener('click', async () => {
        const names = await api('/events/names');
        showModal('Add Widget', `
            <form id="add-widget-form">
                <div class="form-group">
                    <label>Title</label>
                    <input type="text" id="widget-title" required placeholder="Widget Title">
                </div>
                <div class="form-group">
                    <label>Type</label>
                    <select id="widget-type">
                        <option value="line">Line Chart</option>
                        <option value="bar">Bar Chart</option>
                        <option value="pie">Pie Chart</option>
                        <option value="kpi">KPI Card</option>
                        <option value="table">Table</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>Event Name</label>
                    <select id="widget-event">
                        ${names.map(n => `<option value="${n}">${n}</option>`).join('')}
                    </select>
                </div>
                <div class="form-group">
                    <label>Aggregation</label>
                    <select id="widget-agg">
                        <option value="count">Count</option>
                        <option value="sum">Sum</option>
                        <option value="avg">Average</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>Group By (property name, for pie/bar)</label>
                    <input type="text" id="widget-group" placeholder="e.g. page, source">
                </div>
                <div class="form-group">
                    <label>Time Range</label>
                    <select id="widget-range">
                        <option value="1h">1 Hour</option>
                        <option value="24h">24 Hours</option>
                        <option value="7d" selected>7 Days</option>
                        <option value="30d">30 Days</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>Width (columns, 1-12)</label>
                    <input type="number" id="widget-w" value="6" min="1" max="12">
                </div>
                <div class="form-group">
                    <label>Height (rows, 1-8)</label>
                    <input type="number" id="widget-h" value="4" min="1" max="8">
                </div>
                <button type="submit" class="btn btn-primary btn-full">Add Widget</button>
            </form>
        `);
        document.getElementById('add-widget-form').addEventListener('submit', async (e) => {
            e.preventDefault();
            try {
                await api(`/dashboards/${state.currentDashboard.id}/widgets`, {
                    method: 'POST',
                    body: JSON.stringify({
                        title: document.getElementById('widget-title').value,
                        widget_type: document.getElementById('widget-type').value,
                        event_name: document.getElementById('widget-event').value,
                        aggregation: document.getElementById('widget-agg').value,
                        group_by: document.getElementById('widget-group').value || null,
                        time_range: document.getElementById('widget-range').value,
                        time_bucket: '1h',
                        grid_w: parseInt(document.getElementById('widget-w').value),
                        grid_h: parseInt(document.getElementById('widget-h').value),
                    }),
                });
                closeModal();
                showToast('Widget added!', 'success');
                await openDashboard(state.currentDashboard.id);
            } catch (err) {
                showToast(err.message, 'error');
            }
        });
    });

    // Share Dashboard
    document.getElementById('share-dashboard-btn').addEventListener('click', async () => {
        if (!state.currentDashboard) return;
        try {
            const updated = await api(`/dashboards/${state.currentDashboard.id}`, {
                method: 'PATCH',
                body: JSON.stringify({ is_public: true }),
            });
            const shareUrl = `${window.location.origin}/api/dashboards/public/${updated.public_token}`;
            showModal('Share Dashboard', `
                <p>Your dashboard is now public. Share this link:</p>
                <div class="form-group" style="margin-top:1rem">
                    <input type="text" value="${shareUrl}" readonly onclick="this.select()" style="font-family:monospace;font-size:0.85rem">
                </div>
                <p class="text-muted">Anyone with this link can view the dashboard (read-only).</p>
            `);
            showToast('Dashboard shared!', 'success');
        } catch (err) {
            showToast(err.message, 'error');
        }
    });

    // Back to dashboards
    document.getElementById('back-to-dashboards').addEventListener('click', () => {
        if (state.autoRefreshInterval) clearInterval(state.autoRefreshInterval);
        state.currentDashboard = null;
        loadDashboards();
    });

    // Create Alert
    document.getElementById('create-alert-btn').addEventListener('click', async () => {
        const names = await api('/events/names');
        showModal('Create Alert Rule', `
            <form id="create-alert-form">
                <div class="form-group">
                    <label>Name</label>
                    <input type="text" id="alert-name" required placeholder="High Error Rate">
                </div>
                <div class="form-group">
                    <label>Event Name</label>
                    <select id="alert-event">
                        ${names.map(n => `<option value="${n}">${n}</option>`).join('')}
                    </select>
                </div>
                <div class="form-group">
                    <label>Metric</label>
                    <select id="alert-metric">
                        <option value="count">Count</option>
                        <option value="sum">Sum</option>
                        <option value="avg">Average</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>Condition</label>
                    <select id="alert-condition">
                        <option value="gt">Greater than</option>
                        <option value="lt">Less than</option>
                        <option value="gte">Greater or equal</option>
                        <option value="lte">Less or equal</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>Threshold</label>
                    <input type="number" id="alert-threshold" required step="0.01" placeholder="100">
                </div>
                <div class="form-group">
                    <label>Window (minutes)</label>
                    <input type="number" id="alert-window" value="10" min="1" max="1440">
                </div>
                <button type="submit" class="btn btn-primary btn-full">Create Alert</button>
            </form>
        `);
        document.getElementById('create-alert-form').addEventListener('submit', async (e) => {
            e.preventDefault();
            try {
                await api('/alerts/rules', {
                    method: 'POST',
                    body: JSON.stringify({
                        name: document.getElementById('alert-name').value,
                        event_name: document.getElementById('alert-event').value,
                        metric: document.getElementById('alert-metric').value,
                        condition: document.getElementById('alert-condition').value,
                        threshold: parseFloat(document.getElementById('alert-threshold').value),
                        window_minutes: parseInt(document.getElementById('alert-window').value),
                    }),
                });
                closeModal();
                showToast('Alert rule created!', 'success');
                await loadAlerts();
            } catch (err) {
                showToast(err.message, 'error');
            }
        });
    });

    // Invite Member
    document.getElementById('invite-member-btn').addEventListener('click', () => {
        showModal('Invite Team Member', `
            <form id="invite-form">
                <div class="form-group">
                    <label>Email</label>
                    <input type="email" id="invite-email" required placeholder="colleague@company.com">
                </div>
                <div class="form-group">
                    <label>Role</label>
                    <select id="invite-role">
                        <option value="viewer">Viewer</option>
                        <option value="analyst">Analyst</option>
                        <option value="admin">Admin</option>
                    </select>
                </div>
                <button type="submit" class="btn btn-primary btn-full">Send Invitation</button>
            </form>
        `);
        document.getElementById('invite-form').addEventListener('submit', async (e) => {
            e.preventDefault();
            try {
                await api('/auth/invite', {
                    method: 'POST',
                    body: JSON.stringify({
                        email: document.getElementById('invite-email').value,
                        role: document.getElementById('invite-role').value,
                    }),
                });
                closeModal();
                showToast('Invitation sent!', 'success');
            } catch (err) {
                showToast(err.message, 'error');
            }
        });
    });

    // Create API Key
    document.getElementById('create-key-btn').addEventListener('click', () => {
        showModal('Generate API Key', `
            <form id="create-key-form">
                <div class="form-group">
                    <label>Key Name</label>
                    <input type="text" id="key-name" required placeholder="Production API Key">
                </div>
                <button type="submit" class="btn btn-primary btn-full">Generate Key</button>
            </form>
            <div id="key-result" class="hidden" style="margin-top:1rem"></div>
        `);
        document.getElementById('create-key-form').addEventListener('submit', async (e) => {
            e.preventDefault();
            try {
                const result = await api('/api-keys/', {
                    method: 'POST',
                    body: JSON.stringify({ name: document.getElementById('key-name').value }),
                });
                document.getElementById('key-result').classList.remove('hidden');
                document.getElementById('key-result').innerHTML = `
                    <div class="settings-card" style="background:var(--success-bg);border-color:rgba(16,185,129,0.3)">
                        <p style="color:var(--success);font-weight:600;margin-bottom:0.5rem">⚠️ Copy this key now — it won't be shown again!</p>
                        <input type="text" value="${result.key}" readonly onclick="this.select()" style="font-family:monospace;font-size:0.8rem">
                    </div>
                `;
                showToast('API key created!', 'success');
            } catch (err) {
                showToast(err.message, 'error');
            }
        });
    });

    // CSV Upload
    const uploadArea = document.getElementById('csv-upload-area');
    const fileInput = document.getElementById('csv-file-input');

    uploadArea.addEventListener('click', () => fileInput.click());
    uploadArea.addEventListener('dragover', (e) => { e.preventDefault(); uploadArea.style.borderColor = 'var(--accent)'; });
    uploadArea.addEventListener('dragleave', () => { uploadArea.style.borderColor = ''; });
    uploadArea.addEventListener('drop', async (e) => {
        e.preventDefault();
        uploadArea.style.borderColor = '';
        const file = e.dataTransfer.files[0];
        if (file) await uploadCSV(file);
    });
    fileInput.addEventListener('change', async (e) => {
        if (e.target.files[0]) await uploadCSV(e.target.files[0]);
    });
}

async function uploadCSV(file) {
    const formData = new FormData();
    formData.append('file', file);

    try {
        const resp = await fetch(`${API_BASE}/events/ingest/csv`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${state.token}` },
            body: formData,
        });
        const result = await resp.json();
        const resultEl = document.getElementById('csv-upload-result');
        resultEl.classList.remove('hidden');
        resultEl.innerHTML = `
            <div class="settings-card" style="margin-top:1rem">
                <p>✅ Ingested: <strong>${result.ingested}</strong> events</p>
                <p>❌ Errors: <strong>${result.errors || 0}</strong></p>
            </div>
        `;
        showToast(`CSV uploaded: ${result.ingested} events`, 'success');
    } catch (err) {
        showToast('CSV upload failed', 'error');
    }
}

async function deleteWidget(widgetId) {
    if (!confirm('Remove this widget?')) return;
    try {
        await api(`/dashboards/${state.currentDashboard.id}/widgets/${widgetId}`, { method: 'DELETE' });
        showToast('Widget removed', 'success');
        await openDashboard(state.currentDashboard.id);
    } catch (err) {
        showToast(err.message, 'error');
    }
}

// ── WebSocket ────────────────────────────────────────────────────────

function connectWebSockets() {
    if (!state.token) return;

    // Dashboard updates
    try {
        state.ws = new WebSocket(`${wsBase}/dashboard?token=${state.token}`);
        state.ws.onmessage = (e) => {
            const msg = JSON.parse(e.data);
            if (msg.type === 'dashboard_update' && state.currentDashboard) {
                openDashboard(state.currentDashboard.id);
            }
        };
        state.ws.onclose = () => {
            setTimeout(connectWebSockets, 5000);
        };
    } catch (err) {
        console.warn('WS dashboard error:', err);
    }

    // Event stream
    try {
        state.wsEvents = new WebSocket(`${wsBase}/events?token=${state.token}`);
        state.wsEvents.onmessage = (e) => {
            if (state.streamPaused) return;
            const msg = JSON.parse(e.data);
            if (msg.type === 'new_event') {
                state.eventStream.unshift(msg.data);
                if (state.eventStream.length > 100) state.eventStream.pop();
                if (state.currentPage === 'events') renderEventStream();
            }
        };
    } catch (err) {
        console.warn('WS events error:', err);
    }

    // Alert notifications
    try {
        state.wsAlerts = new WebSocket(`${wsBase}/alerts?token=${state.token}`);
        state.wsAlerts.onmessage = (e) => {
            const msg = JSON.parse(e.data);
            if (msg.type === 'alert_triggered') {
                showToast(`🚨 Alert: ${msg.data.name || 'Alert triggered'}`, 'error');
                const badge = document.getElementById('alert-badge');
                badge.classList.remove('hidden');
                badge.textContent = parseInt(badge.textContent || 0) + 1;
            }
        };
    } catch (err) {
        console.warn('WS alerts error:', err);
    }

    // Update status
    updateConnectionStatus(true);
}

function disconnectWebSockets() {
    state.ws?.close();
    state.wsEvents?.close();
    state.wsAlerts?.close();
    updateConnectionStatus(false);
}

function updateConnectionStatus(connected) {
    const el = document.getElementById('connection-status');
    const dot = el.querySelector('.status-dot');
    const text = el.querySelector('span:last-child');
    if (connected) {
        dot.style.background = 'var(--success)';
        text.textContent = 'Connected';
    } else {
        dot.style.background = 'var(--danger)';
        text.textContent = 'Disconnected';
    }
}

// ── Event Filters ────────────────────────────────────────────────────

function initEventFilters() {
    document.getElementById('event-name-filter').addEventListener('change', loadEventStream);
    document.getElementById('pause-stream-btn').addEventListener('click', () => {
        state.streamPaused = !state.streamPaused;
        const btn = document.getElementById('pause-stream-btn');
        btn.innerHTML = state.streamPaused
            ? '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg> Resume'
            : '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg> Pause';
    });

    document.getElementById('overview-time-range').addEventListener('change', loadOverviewCharts);
}

// ── Utilities ────────────────────────────────────────────────────────

function formatNumber(n) {
    if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
    if (n >= 1000) return (n / 1000).toFixed(1) + 'K';
    return n.toString();
}

function formatTime(ts) {
    const d = new Date(ts);
    return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
}

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

// ── Init ─────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', async () => {
    initAuth();
    initNavigation();
    initModals();
    initEventFilters();

    // Auto-login if token exists
    if (state.token) {
        try {
            await enterApp();
        } catch {
            logout();
        }
    }
});
