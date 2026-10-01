"""Main API router to aggregates all sub-routers."""

from __future__ import annotations

from fastapi import APIRouter

from backend.api.admin import router as admin_router
from backend.api.auth import router as auth_router
from backend.api.applications import router as applications_router
from backend.api.cover_letter import router as cover_letter_router
from backend.api.ats import router as ats_router
from backend.api.career import router as career_router
from backend.api.chat import router as chat_router
from backend.api.interview import router as interview_router
from backend.api.jobs import router as jobs_router
from backend.api.resume import router as resume_router
from backend.api.resume_optimizer import router as resume_optimizer_router
from backend.api.reviews import router as reviews_router

api_router = APIRouter(prefix="/api")

api_router.include_router(auth_router, tags=["Auth"])
api_router.include_router(admin_router, tags=["Admin"])
api_router.include_router(resume_router, tags=["Resumes"])
api_router.include_router(resume_optimizer_router, tags=["Resume Optimizer"])
api_router.include_router(jobs_router, tags=["Jobs"])
api_router.include_router(ats_router, tags=["ATS"])
api_router.include_router(career_router, tags=["Career"])
api_router.include_router(interview_router, tags=["Interviews"])
api_router.include_router(chat_router, tags=["Chat"])
api_router.include_router(applications_router, tags=["Applications"])
api_router.include_router(cover_letter_router, tags=["Cover Letters"])
api_router.include_router(reviews_router, tags=["Reviews"])
