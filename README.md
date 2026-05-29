# RoadSide Agent

Fully agentic global roadside assistance platform.

A driver breaks down anywhere in the world → an autonomous multi-agent system diagnoses the issue, finds the nearest verified provider, dispatches them, tracks the job, and closes the loop. No human dispatcher in the middle.

## Architecture

Eight specialized AI agents — each with its own persona, goal, and tool allow-list — coordinate end-to-end:

- **GuardrailAgent** — gates every user input; blocks prompt injection
- **OrchestratorAgent** — root coordinator; delegates to sub-agents
- **TriageAgent** — diagnoses vehicle issue from image, voice, or text
- **DispatchAgent** — finds and assigns nearest provider via PostGIS KNN
- **CommunicationAgent** — contextual SMS/WhatsApp via Twilio
- **TrackingAgent** — detects provider offline / stalled jobs
- **EscalationAgent** — autonomous failure recovery
- **AdminAgent** — natural-language admin queries and safe overrides

See `SCOPE.md`, `PRD.md`, `SPEC.md`, and `CHECKLIST.md` for full design.

## Stack

| Layer | Tech |
|-------|------|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2 (async), Alembic |
| DB | PostgreSQL 16 + PostGIS 3.4 |
| Queue | Celery 5 + Redis 7 |
| AI | Anthropic Claude API |
| Maps | OpenRouteService (OpenStreetMap, free, global) |
| Notifications | Twilio SMS + WhatsApp (180+ countries) |
| Frontend | React 18 + Vite + TailwindCSS (three SPAs) |
| Observability | Prometheus + Grafana |

## Quick start (local development)

Prerequisites: Docker Desktop **running**, Python 3.12, `uv` (recommended) or pip, Node 20+

### 1. Clone and configure

```powershell
git clone <repo-url> roadside-agent
cd roadside-agent
Copy-Item .env.example .env
# Edit .env — fill in: ANTHROPIC_API_KEY, ORS_API_KEY, TWILIO_*
```

### 2. Install Python dependencies into the venv

```powershell
uv pip install -r backend/requirements.txt
```

### 3. Bring up data layer (Postgres + PostGIS, Redis)

```powershell
docker compose -f infrastructure/docker-compose.yml --env-file .env up -d postgres redis
docker compose -f infrastructure/docker-compose.yml ps   # both should be "healthy"
```

### 4. Run database migrations

```powershell
cd backend
..\.venv\Scripts\python.exe -m alembic upgrade head
```

Expected: `INFO  [alembic.runtime.migration] Running upgrade  -> 0001, Initial schema...`

### 5. Seed deterministic test data

```powershell
..\.venv\Scripts\python.exe seed.py
```

Expected output ends with:
```
KNN nearest providers from SF downtown (37.7749, -122.4194):
  - Tom Mechanic: 0.00 km
  - Sarah TowTruck: 1.43 km
  - Mike TireBattery: 4.42 km
```

If the KNN order matches (Tom → Sarah → Mike), PostGIS + GiST index are working correctly.

### Test credentials (after seed)

| Role | Phone | Password |
|------|-------|----------|
| Admin | `+15550000001` | `admin123` |
| Customer | `+15551000001` | `customer123` |
| Customer | `+15551000002` | `customer123` |
| Provider (mechanic, SF downtown) | `+15552000001` | `provider123` |
| Provider (tow, 1.4km away) | `+15552000002` | `provider123` |
| Provider (tire, 4.4km away) | `+15552000003` | `provider123` |

## Repo layout

```
backend/        FastAPI app, agents, tools, Celery workers
frontend/       Three React SPAs (customer, provider, admin)
infrastructure/ Docker Compose, Prometheus, Grafana, Nginx
SCOPE.md        Project scope and success metrics
PRD.md          Product requirements
SPEC.md         Technical blueprint
CHECKLIST.md    Step-by-step implementation plan
```
