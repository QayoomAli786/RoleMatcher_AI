"""Deterministic job normalization from multiple sources → Job schema."""

from __future__ import annotations

import re
from datetime import datetime

from backend.core.schemas import Job

# ── Skill Keywords for Extraction ─────────────────────────────────────────────

_TECH_KEYWORDS: set[str] = {
    "python", "javascript", "typescript", "java", "c++", "c#", "go", "golang",
    "rust", "ruby", "php", "swift", "kotlin", "scala", "r", "sql", "html", "css",
    "react", "angular", "vue", "vue.js", "next.js", "nextjs", "node.js", "nodejs",
    "express", "fastapi", "flask", "django", "spring", "spring boot",
    "docker", "kubernetes", "k8s", "terraform", "aws", "gcp", "azure",
    "postgres", "postgresql", "mysql", "mongodb", "redis", "elasticsearch",
    "graphql", "rest", "grpc", "kafka", "rabbitmq", "airflow",
    "machine learning", "deep learning", "nlp", "computer vision",
    "tensorflow", "pytorch", "scikit-learn", "pandas", "numpy",
    "git", "ci/cd", "jenkins", "github actions", "gitlab ci",
    "linux", "bash", "shell", "ansible", "puppet",
    "ci/cd", "agile", "scrum", "kanban",
    "figma", "sketch", "adobe xd",
    "react native", "flutter", "ios", "android",
    "blockchain", "web3", "solidity",
    "datadog", "grafana", "prometheus", "splunk",
    "spark", "hadoop", "hive", "snowflake", "bigquery", "redshift",
    "airtable", "notion", "jira", "confluence",
    "openai", "langchain", "llm", "gpt", "rag", "vector database",
    "huggingface", "transformers", "mlops", "mlflow",
}

_TITLE_SENIORITY: dict[str, str] = {
    "junior": "junior", "jr": "junior", "entry": "junior", "associate": "junior",
    "mid": "mid", "intermediate": "mid", "mid-level": "mid",
    "senior": "senior", "sr": "senior", "sr.": "senior",
    "lead": "lead", "principal": "lead", "staff": "lead", "head": "lead",
    "director": "lead", "vp": "lead",
}

_EMPLOYMENT_TYPES: dict[str, str] = {
    "full-time": "full-time", "fulltime": "full-time", "full time": "full-time",
    "part-time": "part-time", "parttime": "part-time", "part time": "part-time",
    "contract": "contract", "freelance": "contract", "1099": "contract",
    "intern": "internship", "internship": "internship",
    "temporary": "contract", "temp": "contract",
}

# ── Salary Parsing ────────────────────────────────────────────────────────────

_SALARY_RE = re.compile(
    r"\$\s*(\d[\d,]*(?:\.\d+)?)\s*(k|K)?\s*(?:[-–—to]+)\s*\$?\s*(\d[\d,]*(?:\.\d+)?)\s*(k|K)?",
    re.IGNORECASE,
)
_SINGLE_SALARY_RE = re.compile(
    r"\$\s*(\d[\d,]*(?:\.\d+)?)\s*(k|K)?",
    re.IGNORECASE,
)

_CURRENCY_SYMBOLS = {
    "$": "USD", "€": "EUR", "£": "GBP", "₹": "INR", "¥": "JPY",
}


def _parse_salary_range(text: str) -> tuple[int | None, int | None, str]:
    """Parse salary from text. Returns (min, max, currency)."""
    if not text:
        return None, None, "USD"

    m = _SALARY_RE.search(text)
    if m:
        lo = float(m.group(1).replace(",", "")) * (1000 if m.group(2) else 1)
        hi = float(m.group(3).replace(",", "")) * (1000 if m.group(4) else 1)
        return int(lo), int(hi), "USD"

    m2 = _SINGLE_SALARY_RE.search(text)
    if m2:
        val = float(m2.group(1).replace(",", "")) * (1000 if m2.group(2) else 1)
        return int(val), int(val), "USD"

    return None, None, "USD"


# ── Location Normalization ────────────────────────────────────────────────────

_REMOTE_KEYWORDS = {"remote", "fully remote", "100% remote", "distributed", "anywhere", "global", "worldwide"}


def _normalize_location(raw: str) -> tuple[str, bool]:
    """Returns (normalized_location, is_remote)."""
    if not raw:
        return "", False

    lower = raw.strip().lower()
    for kw in _REMOTE_KEYWORDS:
        if kw in lower:
            return "Remote", True

    location = raw.strip()
    return location, False


def _normalize_employment_type(raw: str) -> str:
    lower = raw.strip().lower()
    for key, val in _EMPLOYMENT_TYPES.items():
        if key in lower:
            return val
    return "full-time"


def _normalize_seniority(title: str, raw: str = "") -> str:
    combined = f"{title} {raw}".lower()
    for key, val in _TITLE_SENIORITY.items():
        if key in combined:
            return val
    return "mid"


def _extract_skills_from_text(text: str) -> list[str]:
    """Extract known tech skills from job description."""
    text_lower = text.lower()
    found: list[str] = []
    seen: set[str] = set()
    for kw in sorted(_TECH_KEYWORDS, key=len, reverse=True):
        if kw not in seen and kw in text_lower:
            found.append(kw)
            seen.add(kw)
    return found


# ── Source Normalizers ────────────────────────────────────────────────────────


def normalize_remotive_job(raw: dict) -> Job:
    """Normalize a Remotive API job listing."""
    location, remote = _normalize_location(raw.get("candidate_required_location", "Remote"))
    salary_min, salary_max, currency = _parse_salary_range(raw.get("salary", ""))
    title = raw.get("title", "")
    desc = raw.get("description", "")
    tags = raw.get("tags", [])
    if isinstance(tags, list):
        skills = [t.lower().strip() for t in tags if isinstance(t, str)]
    else:
        skills = _extract_skills_from_text(desc)

    posted = None
    if raw.get("publication_date"):
        try:
            posted = datetime.fromisoformat(raw["publication_date"].replace("Z", "+00:00"))
        except (ValueError, TypeError):
            pass

    return Job(
        source="remotive",
        source_job_id=str(raw.get("id", "")),
        title=title,
        company=raw.get("company_name", ""),
        location=location or "Remote",
        remote=True,
        description=desc,
        skills=skills,
        salary_min=salary_min,
        salary_max=salary_max,
        currency=currency,
        employment_type=_normalize_employment_type(raw.get("job_type", "")),
        seniority=_normalize_seniority(title),
        posted_at=posted,
        source_url=raw.get("url", ""),
    )


def normalize_jobicy_job(raw: dict) -> Job:
    """Normalize a Jobicy API job listing."""
    location, remote = _normalize_location(raw.get("job_location", ""))
    salary_min, salary_max, currency = _parse_salary_range(
        f"${raw.get('annual_salary_min', '')} - ${raw.get('annual_salary_max', '')}"
    )
    title = raw.get("job_title", "")
    desc = raw.get("job_description", "")
    skills = _extract_skills_from_text(desc)

    posted = None
    if raw.get("pubDate"):
        try:
            posted = datetime.strptime(raw["pubDate"], "%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            pass

    return Job(
        source="jobicy",
        source_job_id=str(raw.get("id", "")),
        title=title,
        company=raw.get("company_name", ""),
        location=location or "Remote",
        remote=remote or raw.get("job_type", "").lower() == "remote",
        description=desc,
        skills=skills,
        salary_min=salary_min,
        salary_max=salary_max,
        currency=currency or "USD",
        employment_type=_normalize_employment_type(raw.get("job_type", "")),
        seniority=_normalize_seniority(title, raw.get("job_type", "")),
        posted_at=posted,
        source_url=raw.get("url", ""),
    )


def normalize_linkedin_job(raw: dict) -> Job:
    """Normalize a LinkedIn job listing dict."""
    location, remote = _normalize_location(raw.get("location", ""))
    title = raw.get("title", "")
    desc = raw.get("description", "")
    skills = _extract_skills_from_text(desc)

    posted = None
    if raw.get("postedDate"):
        try:
            posted = datetime.fromisoformat(raw["postedDate"].replace("Z", "+00:00"))
        except (ValueError, TypeError):
            pass

    return Job(
        source="linkedin",
        source_job_id=raw.get("jobId", raw.get("id", "")),
        title=title,
        company=raw.get("companyName", raw.get("company", "")),
        location=location or "",
        remote=remote,
        description=desc,
        skills=skills,
        salary_min=raw.get("salaryMin"),
        salary_max=raw.get("salaryMax"),
        currency=raw.get("currency", "USD"),
        employment_type=_normalize_employment_type(raw.get("employmentType", "")),
        seniority=_normalize_seniority(title, raw.get("seniorityLevel", "")),
        posted_at=posted,
        source_url=raw.get("url", raw.get("link", "")),
    )


def normalize_generic_job(raw: dict) -> Job:
    """Normalize a generic job dict with common field names."""
    title_field = _first_nonempty(raw, "title", "job_title", "position", "role", "name")
    company_field = _first_nonempty(raw, "company", "company_name", "employer", "organization")
    location_field = _first_nonempty(raw, "location", "job_location", "city", "region")
    desc_field = _first_nonempty(raw, "description", "job_description", "about", "details", "body")
    url_field = _first_nonempty(raw, "url", "source_url", "link", "apply_url", "job_url")
    salary_raw = _first_nonempty(raw, "salary", "salary_range", "compensation", "pay", "")
    emp_type = _first_nonempty(raw, "employment_type", "job_type", "type", "employmentType", "")
    seniority_raw = _first_nonempty(raw, "seniority", "seniority_level", "level", "experience_level", "")

    location, remote = _normalize_location(location_field)
    salary_min, salary_max, currency = _parse_salary_range(salary_raw)
    skills = _extract_skills_from_text(desc_field)

    posted = None
    for date_field in ("posted_at", "postedDate", "created_at", "date", "pubDate", "published"):
        val = raw.get(date_field)
        if val:
            try:
                posted = datetime.fromisoformat(str(val).replace("Z", "+00:00"))
            except (ValueError, TypeError):
                try:
                    posted = datetime.strptime(str(val)[:10], "%Y-%m-%d")
                except (ValueError, TypeError):
                    pass
            if posted:
                break

    return Job(
        source=raw.get("source", "generic"),
        source_job_id=str(raw.get("id", raw.get("source_job_id", ""))),
        title=title_field,
        company=company_field,
        location=location or "",
        remote=remote,
        description=desc_field,
        skills=skills,
        salary_min=salary_min,
        salary_max=salary_max,
        currency=currency,
        employment_type=_normalize_employment_type(emp_type),
        seniority=_normalize_seniority(title_field, seniority_raw),
        posted_at=posted,
        source_url=url_field,
    )


def extract_skills_from_description(description: str) -> list[str]:
    """Public convenience wrapper."""
    return _extract_skills_from_text(description)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _first_nonempty(d: dict, *keys: str, default: str = "") -> str:
    for k in keys:
        val = d.get(k)
        if val is not None and str(val).strip():
            return str(val).strip()
    return default
