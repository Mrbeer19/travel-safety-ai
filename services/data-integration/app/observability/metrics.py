"""Bounded-cardinality service counters."""

from prometheus_client import Counter, Histogram

http_requests = Counter(
    "integration_http_requests_total", "HTTP requests", ["method", "route", "status"]
)
http_latency = Histogram("integration_http_duration_seconds", "HTTP latency", ["method", "route"])
quarantined = Counter("integration_quarantined_total", "Quarantined records", ["error_code"])
