import json
import os
import time
import uuid
from collections import deque
from datetime import datetime, timezone

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse, Response
from prometheus_client import Counter, generate_latest, CONTENT_TYPE_LATEST


# --------------------------------------------------
# 1. Application setup
# --------------------------------------------------

app = FastAPI(title="Production Observability API")

EMAIL = os.getenv("ASSIGNMENT_EMAIL", "23f2002788@ds.study.iitm.ac.in")

startup_time = time.monotonic()

# Prometheus automatically exposes this as
# http_requests_total in its text output.
REQUEST_COUNTER = Counter(
    "http_requests",
    "Total number of HTTP requests received",
)

# Keep the most recent 500 log entries in memory.
recent_logs = deque(maxlen=500)


# --------------------------------------------------
# 2. Structured JSON request logging and counting
# --------------------------------------------------

@app.middleware("http")
async def observe_requests(request: Request, call_next):
    request_id = str(uuid.uuid4())
    start = time.monotonic()
    status_code = 500

    # Count every HTTP request, including requests to
    # /metrics, /healthz, /work and /logs/tail.
    REQUEST_COUNTER.inc()

    try:
        response = await call_next(request)
        status_code = response.status_code
        return response

    finally:
        log_entry = {
            "level": "INFO" if status_code < 500 else "ERROR",
            "ts": datetime.now(timezone.utc).isoformat(),
            "path": request.url.path,
            "request_id": request_id,
            "method": request.method,
            "status_code": status_code,
            "duration_ms": round(
                (time.monotonic() - start) * 1000, 3
            ),
        }

        recent_logs.append(log_entry)

        # Emit one structured JSON log line to stdout.
        print(json.dumps(log_entry), flush=True)


# --------------------------------------------------
# 3. Work endpoint
# --------------------------------------------------

@app.get("/work")
async def do_work(n: int = Query(1, ge=0, le=100000)):
    # Perform K units of simple work.
    done = 0
    for _ in range(n):
        done += 1

    return {"email": EMAIL, "done": done}


# --------------------------------------------------
# 4. Prometheus metrics endpoint
# --------------------------------------------------

@app.get("/metrics")
async def metrics():
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )


# --------------------------------------------------
# 5. Health check endpoint
# --------------------------------------------------

@app.get("/healthz")
async def health():
    uptime = max(0.0, time.monotonic() - startup_time)

    return {
        "status": "ok",
        "uptime_s": float(uptime),
    }


# --------------------------------------------------
# 6. Recent structured logs endpoint
# --------------------------------------------------

@app.get("/logs/tail")
async def logs_tail(
    limit: int = Query(10, ge=1, le=500)
):
    # Newest entries first.
    entries = list(recent_logs)[-limit:][::-1]
    return JSONResponse(content=entries)


# --------------------------------------------------
# 7. Optional root endpoint
# --------------------------------------------------

@app.get("/")
async def root():
    return {
        "message": "Production Observability API is running",
        "endpoints": [
            "/work?n=5",
            "/metrics",
            "/healthz",
            "/logs/tail?limit=10",
        ],
    }