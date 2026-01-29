from __future__ import annotations

import time
from typing import Optional

from fastapi import Request
from fastapi.responses import PlainTextResponse

try:
    from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST  # type: ignore
except Exception:  # pragma: no cover
    Counter = None
    Histogram = None
    generate_latest = None
    CONTENT_TYPE_LATEST = "text/plain; version=0.0.4"


if Counter is not None:
    HTTP_REQUESTS_TOTAL = Counter(
        "vsc_http_requests_total",
        "HTTP requests total",
        ["path", "method", "status"],
    )
    HTTP_REQUEST_DURATION = Histogram(
        "vsc_http_request_duration_seconds",
        "HTTP request duration seconds",
        ["path", "method"],
    )
else:  # pragma: no cover
    HTTP_REQUESTS_TOTAL = None
    HTTP_REQUEST_DURATION = None


def _label_path(request: Request) -> str:
    # Stable enough for now; later you can normalize to route templates.
    return request.url.path


class MetricsMiddleware:
    async def __call__(self, request: Request, call_next):
        t0 = time.time()
        status = "500"
        try:
            resp = await call_next(request)
            status = str(getattr(resp, "status_code", 200))
            return resp
        finally:
            dt = time.time() - t0
            if HTTP_REQUESTS_TOTAL is not None:
                path = _label_path(request)
                method = request.method.upper()
                HTTP_REQUESTS_TOTAL.labels(path=path, method=method, status=status).inc()
                HTTP_REQUEST_DURATION.labels(path=path, method=method).observe(dt)


def metrics_response() -> PlainTextResponse:
    if generate_latest is None:  # pragma: no cover
        return PlainTextResponse("", media_type=CONTENT_TYPE_LATEST)
    data = generate_latest()
    return PlainTextResponse(data.decode("utf-8"), media_type=CONTENT_TYPE_LATEST)
