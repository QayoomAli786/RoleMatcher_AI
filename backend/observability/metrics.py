"""In-memory performance metrics."""

from __future__ import annotations

import time
import threading
from collections import defaultdict


class MetricsStore:
    """Thread-safe in-memory counters and latency averages."""

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

    # ── Uptime ───────────────────────────────────────────────────────────

    def uptime(self) -> float:
        return round(time.time() - self._start_time, 2)


# ── Global singleton ─────────────────────────────────────────────────────────

metrics = MetricsStore()
