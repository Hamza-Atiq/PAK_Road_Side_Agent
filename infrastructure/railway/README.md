# Railway deployment guide

This directory documents how RoadSide Agent's backend is provisioned on Railway.

## Services (one Railway project, multiple services)

| Service | Image | Start command | Healthcheck |
|---|---|---|---|
| `api` | `backend/Dockerfile.railway` | `uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 4` | `GET /health` |
| `worker` | `backend/Dockerfile.railway` | `celery -A celery_worker worker --loglevel=info --concurrency=4 -Q incidents,notifications,monitoring` | — |
| `beat` | `backend/Dockerfile.railway` | `celery -A celery_worker beat --loglevel=info` | — |
| `postgres` | `postgis/postgis:16-3.4` (Docker Hub) | default | `pg_isready` |
| `redis` | `redis:7-alpine` (Docker Hub) | default | `redis-cli ping` |

## One-time setup

1. **Workspace + project** — `railway login`, then `railway init` from repo root (or use Dashboard).
2. **Postgres + PostGIS** — Add a custom service from Docker image `postgis/postgis:16-3.4`. Set:
   - `POSTGRES_USER=roadside`
   - `POSTGRES_PASSWORD=<generate>`
   - `POSTGRES_DB=roadside`
   - Volume: `/var/lib/postgresql/data`
3. **Redis** — Add a Railway Redis plugin (or Docker image `redis:7-alpine`).
4. **Backend services** — Three services pointing at this repo, root `/`, Dockerfile path `backend/Dockerfile.railway`. Override start commands per the table above.
5. **Env vars** (set on all three backend services unless noted):
   ```
   DATABASE_URL=postgresql+asyncpg://roadside:<pw>@${postgres.RAILWAY_PRIVATE_DOMAIN}:5432/roadside
   REDIS_URL=redis://${redis.RAILWAY_PRIVATE_DOMAIN}:6379/0
   CELERY_BROKER_URL=redis://${redis.RAILWAY_PRIVATE_DOMAIN}:6379/1
   CELERY_RESULT_BACKEND=redis://${redis.RAILWAY_PRIVATE_DOMAIN}:6379/2
   ANTHROPIC_API_KEY=sk-ant-...
   JWT_SECRET=<openssl rand -hex 64>
   ENCRYPTION_KEY=<openssl rand -hex 32>
   TWILIO_ACCOUNT_SID=...
   TWILIO_AUTH_TOKEN=...
   TWILIO_PHONE_NUMBER=+1...
   ORS_API_KEY=...                      # OpenRouteService (free tier)
   CORS_ORIGINS=https://app.roadsideagent.com,https://admin.roadsideagent.com
   ENVIRONMENT=production
   DEBUG=false
   ```
6. **First deploy** — push to GitHub main; Railway auto-deploys.
7. **Run migrations + seed (one-off)**:
   ```bash
   railway run --service api alembic upgrade head
   railway run --service api python seed.py
   ```
8. **Custom domain** — In Railway → api service → Domains, attach `api.roadsideagent.com`.
9. **Healthcheck verify** — `curl https://api.roadsideagent.com/health` → `{"status":"ok"}`.

## Scaling

- Increase `api` replicas behind Railway's load balancer (each gets its own in-process WebSocket pubsub — clients reconnect to whichever replica).
- `worker` scales horizontally (multiple replicas, each pulls from Redis).
- `beat` stays at exactly **one replica** (multiple beats would re-fire scheduled tasks).

## Reading metrics

`api`'s `/metrics` endpoint exposes Prometheus format. Connect a Prometheus pull or Grafana Cloud free tier and add the v1 dashboard JSON from `infrastructure/grafana/dashboards/`.

## Cost (early-stage estimate)

- Postgres (1 GB, 1 vCPU): ~$5/mo
- Redis (256 MB): ~$1/mo
- 3× backend services (256–512 MB each): ~$10–20/mo
- **Total: $15–30/mo until you hit real traffic.**

Usage scales linearly. See V2_PLAN.md §6 for projections.
