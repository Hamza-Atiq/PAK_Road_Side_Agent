# Load Tests — RoadSide Agent

Target SLO (Phase 16): **20 concurrent incident submissions all processed within 30 s.**

## Prereqs

1. Backend stack up:
   ```powershell
   docker compose -f infrastructure/docker-compose.yml --env-file .env up -d postgres redis
   cd backend
   ..\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
   ```
2. Celery worker + beat (separate terminals):
   ```powershell
   ..\.venv\Scripts\celery.exe -A celery_worker worker --loglevel=info --concurrency=4 \
     -Q incidents,notifications,monitoring
   ..\.venv\Scripts\celery.exe -A celery_worker beat --loglevel=info
   ```
3. DB seeded:
   ```powershell
   ..\.venv\Scripts\python.exe seed.py
   ```

## Run a burst

```powershell
cd backend
..\.venv\Scripts\locust.exe -f tests/load/locustfile.py --host=http://localhost:8000 `
    --users 20 --spawn-rate 20 --run-time 60s --headless `
    --csv=tests/load/results --only-summary
```

Pass criteria (enforced inside `locustfile.py`):
- `POST /api/incidents` median < 1500 ms
- max < 30000 ms
- zero failures

## Verify end-to-end processing

```powershell
..\.venv\Scripts\python.exe tests/load/verify_processed.py `
    --host http://localhost:8000 `
    --phone +15550000001 --password admin123 `
    --window-seconds 120 --max-processing-seconds 30
```

Exits 0 if every incident in the window reached a terminal-ish state
(ASSIGNED / EN_ROUTE / ARRIVED / COMPLETED / CLOSED / NO_PROVIDER) within
30 s of being created.

## Tuning notes

- If the median submission time creeps above 1 s, the bottleneck is almost
  always synchronous work inside the request handler (file write, DB flush) —
  not the agent pipeline, which runs on Celery.
- If many incidents reach `NO_PROVIDER`, the seed only has 3 providers in SF.
  Scale providers up before measuring throughput.
- For sustained load (not a burst), drop `--run-time 60s` and bump
  `--users 100 --spawn-rate 5`.
