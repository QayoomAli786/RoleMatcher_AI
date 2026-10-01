"""Admin and health-check endpoints."""

from __future__ import annotations

import time
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, Request

from backend.core.config import get_settings
from backend.core.schemas import UserProfile
from backend.security.auth import get_current_user
from backend.observability.metrics import metrics

router = APIRouter()
settings = get_settings()


# ── Health ───────────────────────────────────────────────────────────────────


@router.get("/health")
async def health_check():
    """Unauthenticated health check."""
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": settings.app_version,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ── System stats (admin-only) ────────────────────────────────────────────────


@router.get("/admin/stats")
async def system_stats(
    user: UserProfile = Depends(get_current_user),
):
    """Return aggregate observability metrics.  In production, gate behind an admin role."""
    return {
        "uptime_seconds": metrics.uptime(),
        "total_requests": metrics.counter("total_requests"),
        "total_llm_calls": metrics.counter("total_llm_calls"),
        "total_tokens": metrics.counter("total_tokens"),
        "estimated_cost_usd": round(metrics.counter("total_cost_usd"), 4),
        "cache_hits": metrics.counter("cache_hits"),
        "cache_misses": metrics.counter("cache_misses"),
        "avg_latency_ms": round(metrics.avg_latency(), 2),
        "rate_limit_rejections": metrics.counter("rate_limit_rejections"),
    }


# ── Trigger job refresh ──────────────────────────────────────────────────────


@router.post("/admin/refresh-jobs")
async def refresh_jobs(
    background_tasks: BackgroundTasks,
    user: UserProfile = Depends(get_current_user),
):
    """Kick off a background job-refresh cycle."""
    background_tasks.add_task(_refresh_jobs)
    return {"status": "started", "message": "Job refresh triggered in background."}


async def _refresh_jobs() -> None:
    try:
        from backend.graphs.job_graph import job_pipeline

        await job_pipeline.ainvoke({"target_role": "Software Engineer", "query_keywords": []})
    except Exception:
        pass  # best-effort background task
