"""Pydantic models for the CareerCopilot AI system."""

from datetime import date, datetime, timezone
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field


# ── Enums ────────────────────────────────────────────────────────────────────


class SkillCategory(str, Enum):
    technical = "technical"
    soft = "soft"
    language = "language"
    certification = "certification"


class ProficiencyLevel(str, Enum):
    beginner = "beginner"
    intermediate = "intermediate"
    advanced = "advanced"
    expert = "expert"


# ── Resume Sub-models ────────────────────────────────────────────────────────


class Skill(BaseModel):
    name: str
    category: SkillCategory
    proficiency: ProficiencyLevel = ProficiencyLevel.intermediate


class Experience(BaseModel):
    title: str
    company: str
    location: str = ""
    start_date: date
    end_date: date | None = None
    description: str = ""
    skills_used: list[str] = Field(default_factory=list)
    is_current: bool = False


class Education(BaseModel):
    institution: str
    degree: str
    field: str
    start_date: date | None = None
    end_date: date | None = None
    gpa: float | None = None


class Project(BaseModel):
    name: str
    description: str = ""
    technologies: list[str] = Field(default_factory=list)
    url: str | None = None


class Certification(BaseModel):
    name: str
    issuer: str = ""
    date_obtained: date | None = None
    expiry_date: date | None = None


class ContactInfo(BaseModel):
    email: str = ""
    phone: str = ""
    linkedin: str = ""
    github: str = ""
    website: str = ""


class ResumeProfile(BaseModel):
    """Structured resume data extracted by the parsing pipeline."""

    skills: list[Skill] = Field(default_factory=list)
    experience: list[Experience] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    certifications: list[Certification] = Field(default_factory=list)
    years_experience: float = 0.0
    target_roles: list[str] = Field(default_factory=list)
    summary: str = ""
    contact_info: ContactInfo = Field(default_factory=ContactInfo)


# ── Job Models ───────────────────────────────────────────────────────────────


class Job(BaseModel):
    id: UUID | None = None
    source: str = ""
    source_job_id: str = ""
    title: str
    company: str
    location: str = ""
    remote: bool = False
    description: str = ""
    skills: list[str] = Field(default_factory=list)
    salary_min: int | None = None
    salary_max: int | None = None
    currency: str = "USD"
    employment_type: str = ""  # full-time, part-time, contract
    seniority: str = ""  # junior, mid, senior, lead
    posted_at: datetime | None = None
    source_url: str = ""
    embedding_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ── Matching & Scoring ──────────────────────────────────────────────────────


class JobMatch(BaseModel):
    job_id: UUID
    overall_score: float = 0.0
    skill_score: float = 0.0
    experience_score: float = 0.0
    seniority_score: float = 0.0
    location_score: float = 0.0
    salary_score: float = 0.0
    semantic_score: float = 0.0
    reasoning: str = ""
    missing_skills: list[str] = Field(default_factory=list)


class ATSReport(BaseModel):
    """Applicant Tracking System analysis of a resume against a job description."""

    overall_score: float = 0.0
    keyword_score: float = 0.0
    skill_score: float = 0.0
    experience_score: float = 0.0
    semantic_score: float = 0.0
    education_score: float = 0.0
    missing_keywords: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    improved_sections: dict[str, str] = Field(default_factory=dict)


# ── Career Planning ──────────────────────────────────────────────────────────


class SkillGap(BaseModel):
    skill: str
    current_level: ProficiencyLevel | None = None
    required_level: ProficiencyLevel
    priority: int = 0  # 1 = highest
    market_demand: str = ""  # high, medium, low
    learning_resources: list[str] = Field(default_factory=list)


class CareerPlan(BaseModel):
    current_state: str = ""
    target_state: str = ""
    skill_gaps: list[SkillGap] = Field(default_factory=list)
    learning_priorities: list[str] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    timeline: dict[str, str] = Field(default_factory=dict)
    interview_prep: str = ""
    application_strategy: str = ""
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    cache_key: str = ""


# ── Market Intelligence ──────────────────────────────────────────────────────


class MarketSnapshot(BaseModel):
    id: UUID | None = None
    target_role: str
    skill_frequency: dict[str, int] = Field(default_factory=dict)
    role_frequency: dict[str, int] = Field(default_factory=dict)
    seniority_distribution: dict[str, float] = Field(default_factory=dict)
    salary_distribution: dict[str, float] = Field(default_factory=dict)
    remote_percentage: float = 0.0
    technology_trends: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ── Optimized (Tailored) Resume ────────────────────────────────────────────


class OptimizedContact(BaseModel):
    name: str = ""
    email: str = ""
    phone: str = ""
    linkedin: str = ""
    github: str = ""
    website: str = ""


class OptimizedExperience(BaseModel):
    title: str
    company: str
    location: str = ""
    start_date: str = ""
    end_date: str = ""
    is_current: bool = False
    bullets: list[str] = Field(default_factory=list)


class OptimizedEducation(BaseModel):
    institution: str
    degree: str = ""
    field: str = ""
    start_date: str = ""
    end_date: str = ""
    gpa: str = ""


class OptimizedProject(BaseModel):
    name: str
    description: str = ""
    technologies: list[str] = Field(default_factory=list)
    bullets: list[str] = Field(default_factory=list)


class OptimizedCertification(BaseModel):
    name: str
    issuer: str = ""
    date_obtained: str = ""


class OptimizedResume(BaseModel):
    """A resume reframed for a specific job description.

    Contains ONLY facts sourced from the original resume — wording, ordering
    and emphasis change, but no skill, employer, date or metric is invented.
    """

    contact: OptimizedContact = Field(default_factory=OptimizedContact)
    target_role: str = ""
    target_company: str = ""
    headline: str = ""
    summary: str = ""
    skills: list[str] = Field(default_factory=list)
    experience: list[OptimizedExperience] = Field(default_factory=list)
    education: list[OptimizedEducation] = Field(default_factory=list)
    projects: list[OptimizedProject] = Field(default_factory=list)
    certifications: list[OptimizedCertification] = Field(default_factory=list)
    matched_keywords: list[str] = Field(default_factory=list)
    changes: list[str] = Field(default_factory=list)


# ── User ─────────────────────────────────────────────────────────────────────


class UserPreferences(BaseModel):
    target_roles: list[str] = Field(default_factory=list)
    preferred_locations: list[str] = Field(default_factory=list)
    remote_only: bool = False
    salary_min: int | None = None
    salary_max: int | None = None


class UserProfile(BaseModel):
    id: UUID | None = None
    email: str
    name: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    preferences: UserPreferences = Field(default_factory=UserPreferences)
