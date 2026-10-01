"""SQLAlchemy ORM models for CareerCopilot AI."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, DeclarativeBase, mapped_column, relationship

from backend.core.types import JSONB, UUID


class Base(DeclarativeBase):
    pass


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _now() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


def _updated_at() -> Mapped[datetime]:
    return mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


# ── User ─────────────────────────────────────────────────────────────────────


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _uuid_pk()
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str | None] = mapped_column(String(512))
    preferences: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = _updated_at()

    # Relationships
    resumes: Mapped[list["Resume"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    applications: Mapped[list["Application"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    conversations: Mapped[list["Conversation"]] = relationship(back_populates="user", cascade="all, delete-orphan")


# ── Resume ───────────────────────────────────────────────────────────────────


class Resume(Base):
    __tablename__ = "resumes"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    original_filename: Mapped[str | None] = mapped_column(String(512))
    file_path: Mapped[str | None] = mapped_column(String(1024))
    raw_text: Mapped[str | None] = mapped_column(Text)
    parsed_profile: Mapped[dict | None] = mapped_column(JSONB)
    parsing_status: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = _updated_at()

    # Relationships
    user: Mapped["User"] = relationship(back_populates="resumes")
    versions: Mapped[list["ResumeVersion"]] = relationship(back_populates="resume", cascade="all, delete-orphan")
    applications: Mapped[list["Application"]] = relationship(back_populates="resume")


# ── ResumeVersion ────────────────────────────────────────────────────────────


class ResumeVersion(Base):
    __tablename__ = "resume_versions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    resume_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("resumes.id", ondelete="CASCADE"), nullable=False, index=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    target_role: Mapped[str] = mapped_column(String(255), default="")
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    content: Mapped[str | None] = mapped_column(Text)
    parsed_profile: Mapped[dict | None] = mapped_column(JSONB)
    ats_score: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = _now()

    # Relationships
    resume: Mapped["Resume"] = relationship(back_populates="versions")
    skills: Mapped[list["Skill"]] = relationship(back_populates="resume_version", cascade="all, delete-orphan")

    __table_args__ = (Index("ix_resume_version_resume_version", "resume_id", "version_number", unique=True),)


# ── Skill ────────────────────────────────────────────────────────────────────


class Skill(Base):
    __tablename__ = "skills"

    id: Mapped[uuid.UUID] = _uuid_pk()
    resume_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("resume_versions.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    proficiency: Mapped[str] = mapped_column(String(50), default="intermediate")
    created_at: Mapped[datetime] = _now()

    # Relationships
    resume_version: Mapped["ResumeVersion"] = relationship(back_populates="skills")


# ── Job ──────────────────────────────────────────────────────────────────────


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = _uuid_pk()
    source: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    source_job_id: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    company: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    location: Mapped[str] = mapped_column(String(255), default="")
    remote: Mapped[bool] = mapped_column(Boolean, default=False)
    description: Mapped[str | None] = mapped_column(Text)
    skills: Mapped[list | None] = mapped_column(JSONB, default=list)
    salary_min: Mapped[int | None] = mapped_column(Integer)
    salary_max: Mapped[int | None] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    employment_type: Mapped[str] = mapped_column(String(50), default="")
    seniority: Mapped[str] = mapped_column(String(50), default="", index=True)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_url: Mapped[str | None] = mapped_column(String(2048))
    embedding_id: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = _updated_at()

    # Relationships
    matches: Mapped[list["JobMatch"]] = relationship(back_populates="job", cascade="all, delete-orphan")
    applications: Mapped[list["Application"]] = relationship(back_populates="job")

    __table_args__ = (Index("ix_job_source_source_id", "source", "source_job_id", unique=True),)


# ── JobSource ────────────────────────────────────────────────────────────────


class JobSource(Base):
    __tablename__ = "job_sources"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    base_url: Mapped[str | None] = mapped_column(String(2048))
    config: Mapped[dict | None] = mapped_column(JSONB)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _now()


# ── JobMatch ─────────────────────────────────────────────────────────────────


class JobMatch(Base):
    __tablename__ = "job_matches"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    resume_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("resume_versions.id", ondelete="CASCADE"), nullable=False)
    overall_score: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    skill_score: Mapped[float] = mapped_column(Float, default=0.0)
    experience_score: Mapped[float] = mapped_column(Float, default=0.0)
    seniority_score: Mapped[float] = mapped_column(Float, default=0.0)
    location_score: Mapped[float] = mapped_column(Float, default=0.0)
    salary_score: Mapped[float] = mapped_column(Float, default=0.0)
    semantic_score: Mapped[float] = mapped_column(Float, default=0.0)
    reasoning: Mapped[str | None] = mapped_column(Text)
    missing_skills: Mapped[list | None] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = _now()

    # Relationships
    job: Mapped["Job"] = relationship(back_populates="matches")

    __table_args__ = (Index("ix_job_match_user_job", "user_id", "job_id", unique=True),)


# ── ATSReport ────────────────────────────────────────────────────────────────


class ATSReport(Base):
    __tablename__ = "ats_reports"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    resume_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("resume_versions.id", ondelete="CASCADE"), nullable=False)
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    overall_score: Mapped[float] = mapped_column(Float, default=0.0)
    keyword_score: Mapped[float] = mapped_column(Float, default=0.0)
    skill_score: Mapped[float] = mapped_column(Float, default=0.0)
    experience_score: Mapped[float] = mapped_column(Float, default=0.0)
    semantic_score: Mapped[float] = mapped_column(Float, default=0.0)
    education_score: Mapped[float] = mapped_column(Float, default=0.0)
    report_data: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _now()


# ── CareerPlan ───────────────────────────────────────────────────────────────


class CareerPlan(Base):
    __tablename__ = "career_plans"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    target_role: Mapped[str] = mapped_column(String(255), nullable=False)
    plan_data: Mapped[dict | None] = mapped_column(JSONB)
    cache_key: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = _updated_at()


# ── Application ──────────────────────────────────────────────────────────────


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    resume_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("resumes.id", ondelete="SET NULL"))
    resume_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("resume_versions.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(30), default="saved", index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    ats_score: Mapped[float | None] = mapped_column(Float)
    match_score: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = _updated_at()

    # Relationships
    user: Mapped["User"] = relationship(back_populates="applications")
    job: Mapped["Job"] = relationship(back_populates="applications")
    resume: Mapped["Resume | None"] = relationship(back_populates="applications")

    __table_args__ = (Index("ix_application_user_job", "user_id", "job_id", unique=True),)


# ── Interview ────────────────────────────────────────────────────────────────


class Interview(Base):
    __tablename__ = "interviews"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    resume_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("resume_versions.id", ondelete="SET NULL"))
    questions: Mapped[list | None] = mapped_column(JSONB, default=list)
    answers: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    feedback: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    overall_score: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = _updated_at()


# ── Conversation ─────────────────────────────────────────────────────────────


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = _updated_at()

    # Relationships
    user: Mapped["User"] = relationship(back_populates="conversations")
    messages: Mapped[list["ConversationMessage"]] = relationship(back_populates="conversation", cascade="all, delete-orphan")


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"

    id: Mapped[uuid.UUID] = _uuid_pk()
    conversation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tools_used: Mapped[list | None] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = _now()

    # Relationships
    conversation: Mapped["Conversation"] = relationship(back_populates="messages")


# ── ConversationSummary ──────────────────────────────────────────────────────


class ConversationSummary(Base):
    __tablename__ = "conversation_summaries"

    id: Mapped[uuid.UUID] = _uuid_pk()
    conversation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True, unique=True)
    summary_text: Mapped[str] = mapped_column(Text, nullable=False)
    key_topics: Mapped[list | None] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = _now()


# ── CoverLetter ────────────────────────────────────────────────────────────


class CoverLetter(Base):
    __tablename__ = "cover_letters"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    resume_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("resumes.id", ondelete="CASCADE"), nullable=False)
    job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="SET NULL"))
    job_title: Mapped[str] = mapped_column(String(512), default="")
    company_name: Mapped[str] = mapped_column(String(255), default="")
    tone: Mapped[str] = mapped_column(String(50), default="professional")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = _updated_at()


# ── MarketSnapshot ───────────────────────────────────────────────────────────


class MarketSnapshot(Base):
    __tablename__ = "market_snapshots"

    id: Mapped[uuid.UUID] = _uuid_pk()
    target_role: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    skill_frequency: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    role_frequency: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    seniority_distribution: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    salary_distribution: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    remote_percentage: Mapped[float] = mapped_column(Float, default=0.0)
    technology_trends: Mapped[list | None] = mapped_column(JSONB, default=list)
    generated_at: Mapped[datetime] = _now()
