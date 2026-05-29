"""Locust load test — 20 concurrent customers submitting incidents.

Goal (per CHECKLIST Phase 16): 20 concurrent submissions all processed end-to-end
within 30 seconds. "Processed" here means the API returns 201 quickly (the
agent pipeline runs async on Celery). For an end-to-end measurement, the
companion script `verify_processed.py` polls `/api/incidents/{id}` until each
incident reaches ASSIGNED or NO_PROVIDER.

Run interactively (web UI on :8089):

    cd backend
    ..\\.venv\\Scripts\\locust.exe -f tests/load/locustfile.py --host=http://localhost:8000

Or headless for CI / scoring (writes CSV reports):

    ..\\.venv\\Scripts\\locust.exe -f tests/load/locustfile.py --host=http://localhost:8000 \\
        --users 20 --spawn-rate 20 --run-time 60s --headless \\
        --csv=tests/load/results --only-summary

Prerequisites
-------------
1. Backend running on http://localhost:8000 (uvicorn).
2. Celery worker + beat running.
3. Database seeded — login uses the 2 seeded customers; spread across vusers
   round-robin. Phones: +15551000001 / customer123, +15551000002 / customer123.
4. (Optional) Anthropic + ORS keys for full end-to-end timing; if absent the
   agents still complete but with degraded paths.
"""
from __future__ import annotations

import random
import time

from locust import HttpUser, between, events, task


SEED_CUSTOMERS = [
    ("+15551000001", "customer123"),
    ("+15551000002", "customer123"),
]

# Simulate breakdowns spread around downtown SF so PostGIS KNN has work to do.
SF_DOWNTOWN = (37.7749, -122.4194)
DESCRIPTIONS = [
    "Engine won't start, battery seems dead",
    "Flat tire on the rear-right, no spare",
    "Out of fuel, parked on the shoulder",
    "Smoke from the hood, engine overheating",
    "Locked out of my car with keys inside",
    "Brakes squealing loudly, unsafe to drive",
    "Won't shift out of park",
    "Headlights flickering, dashboard warnings",
]


def _jittered_point(base_lat: float, base_lng: float, radius_km: float = 5.0) -> tuple[float, float]:
    """Random point within ~radius_km of the base. 1 deg lat ~= 111 km."""
    drift = radius_km / 111.0
    return (
        base_lat + random.uniform(-drift, drift),
        base_lng + random.uniform(-drift, drift),
    )


class CustomerLoad(HttpUser):
    """One simulated customer reporting an incident."""

    # Hackathon target: bursty submissions, not sustained traffic.
    wait_time = between(0.1, 1.0)

    def on_start(self) -> None:
        """Login once per virtual user; reuse the access token for submissions."""
        phone, password = random.choice(SEED_CUSTOMERS)
        resp = self.client.post(
            "/api/auth/login",
            json={"phone": phone, "password": password},
            name="POST /api/auth/login",
        )
        if resp.status_code != 200:
            # Mark all subsequent requests as failed by detaching the client.
            print(f"[locust] login failed for {phone}: {resp.status_code} {resp.text[:200]}")
            self.environment.runner.quit()
            return
        token = resp.json()["access_token"]
        self.client.headers.update({"Authorization": f"Bearer {token}"})
        self._submitted_ids: list[str] = []

    @task(10)
    def submit_incident(self) -> None:
        lat, lng = _jittered_point(*SF_DOWNTOWN)
        description = random.choice(DESCRIPTIONS)
        # Multipart POST — no media files, just form fields.
        resp = self.client.post(
            "/api/incidents",
            data={
                "lat": lat,
                "lng": lng,
                "description": description,
                "address": f"Test location ({lat:.4f}, {lng:.4f})",
            },
            name="POST /api/incidents",
        )
        if resp.status_code == 201:
            body = resp.json()
            self._submitted_ids.append(body["id"])

    @task(2)
    def list_my_incidents(self) -> None:
        self.client.get("/api/incidents/my?limit=10", name="GET /api/incidents/my")


# ----------------------------------------------------------------------
# Test result summary — fail the locust run if median latency on incident
# submission exceeds 1.5 s or any submission > 30 s.
# ----------------------------------------------------------------------


@events.quitting.add_listener
def _enforce_perf_budget(environment, **_kwargs) -> None:
    stats = environment.stats.get("POST /api/incidents", "POST")
    if stats.num_requests == 0:
        return
    median = stats.median_response_time
    p95 = stats.get_response_time_percentile(0.95)
    max_ms = stats.max_response_time
    print(
        f"\n[locust] POST /api/incidents — count={stats.num_requests} "
        f"median={median} ms  p95={p95} ms  max={max_ms} ms  failures={stats.num_failures}"
    )
    # Fail the run when basic SLOs are missed. Tune as needed.
    if median > 1500:
        environment.process_exit_code = 1
        print(f"[locust] FAIL: median {median} ms > 1500 ms budget")
    if max_ms > 30_000:
        environment.process_exit_code = 1
        print(f"[locust] FAIL: max {max_ms} ms > 30 s budget")
    if stats.num_failures > 0:
        environment.process_exit_code = 1
        print(f"[locust] FAIL: {stats.num_failures} failed submissions")
