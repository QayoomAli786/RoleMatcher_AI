"""In-memory performance metrics with decorator helpers."""

from __future__ import annotations

import time
import threading
from collections import defaultdict
from typing import Any, Callable


class MetricsStore:
    """Thread-safe in-memory metrics collector.

    Supports counters, gauges, histograms (latency), and can be exported
    to Prometheus / OpenTelemetry later.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[str, float] = defaultdict(float)
        self._latencies: dict[str, list[float]] = defaultdict(list)
        self._start_time = time.time()

    # ── Counters ─────────────────────────────────────────────────────────

    def inc(self, name: str, value: float = 1.0) -> None:
        with self._lock:
            self._counters[name] += value

    def counter(self, name: str) -> float:
        with self._lock:
            return self._counters.get(name, 0.0)

    # ── Latency histograms ───────────────────────────────────────────────

    def observe(self, name: str, value_ms: float) -> None:
        with self._lock:
            self._latencies[name].append(value_ms)
            # Keep at most 10 000 samples per metric
            if len(self._latencies[name]) > 10_000:
                self._latencies[name] = self._latencies[name][-10_000:]

    def avg_latency(self, name: str = "request_latency_ms") -> float:
        with self._lock:
            samples = self._latencies.get(name, [])
            return sum(samples) / len(samples) if samples else 0.0

    def p95_latency(self, name: str = "request_latency_ms") -> float:
        with self._lock:
            samples = sorted(self._latencies.get(name, []))
            if not samples:
                return 0.0
            idx = int(len(samples) * 0.95)
            return samples[min(idx, len(samples) - 1)]

    def p99_latency(self, name: str = "request_latency_ms") -> float:
        with self._lock:
            samples = sorted(self._latencies.get(name, []))
            if not samples:
                return 0.0
            idx = int(len(samples) * 0.99)
            return samples[min(idx, len(samples) - 1)]

    # ── Uptime ───────────────────────────────────────────────────────────

    def uptime(self) -> float:
        return round(time.time() - self._start_time, 2)

    # ── Export ────────────────────────────────────────────────────────────

    def snapshot(self) -> dict[str, Any]:
        """Return a JSON-serialisable snapshot of all metrics."""
        with self._lock:
            return {
                "uptime_seconds": self.uptime(),
                "counters": dict(self._counters),
                "latency_avg_ms": {
                    k: round(sum(v) / len(v), 2) if v else 0
                    for k, v in self._latencies.items()
                },
                "latency_p95_ms": {k: self.p95_latency(k) for k in self._latencies},
                "latency_p99_ms": {k: self.p99_latency(k) for k in self._latencies},
            }

    def reset(self) -> None:
        with self._lock:
            self._counters.clear()
            self._latencies.clear()
            self._start_time = time.time()


# ── Global singleton ─────────────────────────────────────────────────────────

metrics = MetricsStore()


# ── Decorator ────────────────────────────────────────────────────────────────


def timed(metric_name: str | None = None):
    """Decorator that records execution time as a latency metric."""

    def decorator(func: Callable) -> Callable:
        name = metric_name or f"{func.__module__}.{func.__qualname__}.latency_ms"

        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            start = time.perf_counter()
            try:
                return await func(*args, **kwargs)
            finally:
                elapsed = (time.perf_counter() - start) * 1000
                metrics.observe(name, elapsed)

        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            start = time.perf_counter()
            try:
                return func(*args, **kwargs)
            finally:
                elapsed = (time.perf_counter() - start) * 1000
                metrics.observe(name, elapsed)

        import asyncio
        if asyncio.iscoroutinefunction(func):
            async_wrapper.__wrapped__ = func  # type: ignore[attr-defined]
            return async_wrapper
        sync_wrapper.__wrapped__ = func  # type: ignore[attr-defined]
        return sync_wrapper

    return decorator
