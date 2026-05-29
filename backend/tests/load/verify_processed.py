"""Companion to locustfile.py — verifies end-to-end processing latency.

After a locust burst, run this against the same backend to confirm every
recently-submitted incident reached a terminal-ish state (ASSIGNED, NO_PROVIDER,
COMPLETED, or CLOSED) within 30 seconds of REPORTED.

Usage:
    cd backend
    ..\\.venv\\Scripts\\python.exe tests/load/verify_processed.py \\
        --host http://localhost:8000 \\
        --phone +15550000001 --password admin123 \\
        --window-seconds 120 \\
        --max-processing-seconds 30
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timedelta, timezone

import httpx

TERMINAL_STATUSES = {"ASSIGNED", "EN_ROUTE", "ARRIVED", "COMPLETED", "CLOSED", "NO_PROVIDER"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="http://localhost:8000")
    parser.add_argument("--phone", default="+15550000001", help="admin phone for full visibility")
    parser.add_argument("--password", default="admin123")
    parser.add_argument("--window-seconds", type=int, default=120,
                        help="only check incidents created within this many seconds ago")
    parser.add_argument("--max-processing-seconds", type=int, default=30,
                        help="fail if any incident takes longer than this to leave REPORTED/ANALYZING")
    args = parser.parse_args()

    with httpx.Client(base_url=args.host, timeout=10.0) as client:
        # Login
        r = client.post("/api/auth/login", json={"phone": args.phone, "password": args.password})
        if r.status_code != 200:
            print(f"[verify] login failed: {r.status_code} {r.text}")
            return 2
        token = r.json()["access_token"]
        client.headers["Authorization"] = f"Bearer {token}"

        cutoff = datetime.now(timezone.utc) - timedelta(seconds=args.window_seconds)
        # Admin: list all recent incidents
        r = client.get("/api/incidents", params={"limit": 100, "offset": 0})
        if r.status_code != 200:
            print(f"[verify] list failed: {r.status_code} {r.text}")
            return 2
        items = r.json().get("items", [])
        recent = [
            i for i in items
            if datetime.fromisoformat(i["created_at"].replace("Z", "+00:00")) >= cutoff
        ]
        if not recent:
            print("[verify] no recent incidents to check — did you run the locust burst?")
            return 1

        print(f"[verify] checking {len(recent)} incidents created in last {args.window_seconds}s")

        slow: list[dict] = []
        stuck: list[dict] = []
        for inc in recent:
            created = datetime.fromisoformat(inc["created_at"].replace("Z", "+00:00"))
            age_seconds = (datetime.now(timezone.utc) - created).total_seconds()
            status = inc["status"]
            if status not in TERMINAL_STATUSES:
                stuck.append({"id": inc["id"], "status": status, "age": int(age_seconds)})
                continue
            if age_seconds > args.max_processing_seconds:
                # We can't see status transition timestamps from the brief list,
                # so this is a conservative bound: if it's still pre-terminal
                # after max_processing_seconds, that's the actual failure case
                # handled above. A terminal status reached after age >
                # max_processing_seconds means SLO breach IF the budget is from
                # creation time.
                slow.append({"id": inc["id"], "status": status, "age": int(age_seconds)})

        print(f"[verify] {len(recent) - len(slow) - len(stuck)} processed within budget")
        if slow:
            print(f"[verify] {len(slow)} processed but slowly:")
            for s in slow[:5]:
                print(f"   - {s['id']} reached {s['status']} after {s['age']}s")
        if stuck:
            print(f"[verify] {len(stuck)} STILL pre-terminal:")
            for s in stuck[:5]:
                print(f"   - {s['id']} status={s['status']} age={s['age']}s")

        return 1 if (stuck or slow) else 0


if __name__ == "__main__":
    sys.exit(main())
