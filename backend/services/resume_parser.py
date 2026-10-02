"""Deterministic resume parsing: PDF/DOCX → ResumeProfile schema."""

from __future__ import annotations

import logging
import re
import unicodedata
from datetime import date
from pathlib import Path

from backend.core.schemas import (
    Certification,
    ContactInfo,
    Education,
    Experience,
    Project,
    ResumeProfile,
    Skill,
    SkillCategory,
)

logger = logging.getLogger(__name__)

# ── Skills Database ───────────────────────────────────────────────────────────

SKILLS_DB: set[str] = {
    # Languages
    "python", "javascript", "typescript", "java", "c++", "c#", "go", "golang",
    "rust", "ruby", "php", "swift", "kotlin", "scala", "r", "matlab", "perl",
    "haskell", "elixir", "clojure", "f#", "fortran", "cobol", "sql", "nosql",
    "html", "css", "scss", "sass", "less", "xml", "json", "yaml", "toml",
    "markdown", "latex", "bash", "shell", "powershell", "zsh", "lua",
    "dart", "objective-c", "assembly", "groovy", "vba", "abap",
    "typescriptreact", "jsx", "tsx", "vue", "svelte",
    # Frontend
    "react", "react.js", "reactjs", "angular", "angularjs", "vue.js", "vuejs",
    "next.js", "nextjs", "nuxt.js", "nuxtjs", "svelte", "sveltekit",
    "tailwind", "tailwindcss", "bootstrap", "material-ui", "mui", "chakra-ui",
    "ant design", "antd", "styled-components", "emotion", "sass",
    "redux", "zustand", "recoil", "jotai", "mobx", "pinia", "vuex",
    "graphql", "apollo", "relay", "webpack", "vite", "esbuild", "rollup",
    "parcel", "turbopack", "storybook", "cypress", "playwright", "puppeteer",
    "jest", "vitest", "mocha", "chai", "jasmine", "testing-library",
    "d3.js", "three.js", "mapbox", "leaflet", "chart.js", "recharts",
    "electron", "tauri", "capacitor", "react native", "flutter",
    # Backend
    "node.js", "nodejs", "express", "express.js", "fastify", "nestjs",
    "django", "flask", "fastapi", "starlette", "uvicorn", "gunicorn",
    "spring", "spring boot", "springboot", "micronaut", "quarkus",
    "rails", "ruby on rails", "laravel", "symfony", "actix", "axum",
    "gin", "echo", "fiber", "actix-web", "rocket", "django rest framework",
    "rest", "restful", "rest api", "grpc", "protobuf", "websocket",
    "http", "https", "tcp", "udp", "dns",
    # Databases
    "postgresql", "postgres", "mysql", "mariadb", "sqlite", "mssql",
    "oracle", "db2", "cassandra", "dynamodb", "dynamo", "cosmosdb",
    "mongodb", "mongo", "redis", "memcached", "elasticsearch", "opensearch",
    "neo4j", "arangodb", "couchdb", "influxdb", "timescaledb",
    "prisma", "sequelize", "typeorm", "knex", "sqlalchemy", "alembic",
    "drizzle", "mongoose", "pg", "psycopg2", "asyncpg", "sqlite3",
    "clickhouse", "snowflake", "bigquery", "redshift", "athena",
    "supabase", "firebase", "planetscale", "neon", "fly.io",
    # Cloud & Infrastructure
    "aws", "amazon web services", "ec2", "s3", "lambda", "ecs", "eks",
    "fargate", "cloudformation", "cdk", "sqs", "sns", "dynamodb",
    "api gateway", "cloudfront", "route53", "iam", "rds", "elasticache",
    "gcp", "google cloud", "gke", "cloud run", "cloud functions", "bigquery",
    "cloud storage", "firestore", "pub/sub", "dataflow", "vertex ai",
    "azure", "azure devops", "aks", "azure functions", "azure sql",
    "cosmosdb", "blob storage", "azure ad", "entra id",
    "vercel", "netlify", "cloudflare", "cloudflare workers", "pages",
    "heroku", "render", "railway", "digitalocean", "linode", "vultr",
    "fly.io", "deno deploy", "bun",
    # DevOps & SRE
    "docker", "docker-compose", "kubernetes", "k8s", "helm", "istio",
    "nginx", "apache", "caddy", "traefik", "envoy",
    "terraform", "pulumi", "ansible", "chef", "puppet", "saltstack",
    "jenkins", "github actions", "gitlab ci", "gitlab-ci", "circleci",
    "travis ci", "argocd", "flux", "tekton", "drone",
    "prometheus", "grafana", "datadog", "new relic", "splunk",
    "elk stack", "elasticsearch", "logstash", "kibana",
    "fluentd", "fluentbit", "jaeger", "opentelemetry", "otel",
    "linux", "bash", "shell scripting", "ssh", "systemd", "cron",
    "load balancing", "reverse proxy", "ssl", "tls", "cdn",
    # AI/ML
    "machine learning", "deep learning", "artificial intelligence",
    "natural language processing", "nlp", "computer vision",
    "tensorflow", "pytorch", "keras", "scikit-learn", "sklearn",
    "hugging face", "huggingface", "transformers", "langchain",
    "openai", "llm", "gpt", "chatgpt", "claude", "gemini",
    "pandas", "numpy", "scipy", "matplotlib", "seaborn", "plotly",
    "jupyter", "notebook", "anaconda", "pip", "conda",
    "neural network", "cnn", "rnn", "lstm", "transformer",
    "reinforcement learning", "supervised learning", "unsupervised learning",
    "feature engineering", "data preprocessing", "model training",
    "fine-tuning", "fine tuning", "rag", "retrieval augmented generation",
    "vector database", "pinecone", "weaviate", "chromadb", "qdrant",
    "mlflow", "wandb", "weights & biases", "dvc", "kubeflow",
    "onnx", "tensorrt", "triton", "mlops",
    # Data Engineering
    "etl", "data pipeline", "apache spark", "spark", "flink",
    "apache kafka", "kafka", "rabbitmq", "apache airflow", "airflow",
    "dbt", "prefect", "dagster", "luigi", "apache beam",
    "data lake", "data warehouse", "lakehouse", "medallion architecture",
    "parquet", "avro", "orc", "delta lake", "iceberg", "hudi",
    "glue", "emr", "athena", "kinesis", "msk",
    # Mobile
    "ios", "android", "react native", "flutter", "dart",
    "swift", "swiftui", "uikit", "xcode",
    "kotlin", "jetpack compose", "android studio",
    "ionic", "capacitor", "xamarin",
    "app store", "play store", "testflight", "fastlane",
    # Security
    "owasp", "penetration testing", "vulnerability assessment",
    "sast", "dast", "saqli", "xss", "csrf", "ssrf",
    "oauth", "oauth2", "jwt", "saml", "oidc",
    "waf", "firewall", "ids", "ips", "siem",
    "encryption", "tls", "ssl", "pki", "certificate management",
    "vault", "secrets management", "cybersecurity",
    # Version Control & Tools
    "git", "github", "gitlab", "bitbucket", "svn",
    "jira", "confluence", "notion", "linear", "asana", "trello",
    "slack", "discord", "zoom", "teams",
    "vscode", "visual studio", "intellij", "vim", "neovim", "emacs",
    "postman", "insomnia", "curl", "httpie",
    "figma", "sketch", "adobe xd", "zeplin", "invision",
    # Methodologies
    "agile", "scrum", "kanban", "sprint", "lean",
    "tdd", "bdd", "pair programming", "code review",
    "ci/cd", "continuous integration", "continuous deployment",
    "microservices", "monolith", "serverless", "event-driven",
    "domain-driven design", "ddd", "solid", "clean architecture",
    "12-factor", "twelve-factor",
    # Soft / Business
    "leadership", "mentoring", "communication", "collaboration",
    "problem solving", "critical thinking", "time management",
    "project management", "stakeholder management", "requirements gathering",
    "technical writing", "presentation", "public speaking",
    # Domain
    "fintech", "healthtech", "edtech", "e-commerce", "saas", "paas",
    "blockchain", "web3", "defi", "smart contracts", "solidity",
    "iot", "internet of things", "embedded systems", "rtos",
    "payments", "stripe", "paypal", "square",
    "graphql", "rest", "grpc", "soap", "websocket", "sse",
}

# ── Text Cleaning ─────────────────────────────────────────────────────────────

def _clean_text(text: str) -> str:
    """Remove excessive whitespace, normalize unicode, fix encoding."""
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("utf-8", errors="replace").decode("utf-8")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3+}", "\n\n", text)
    return text.strip()


# ── In-memory extraction (uploaded bytes, no temp file) ──────────────────────

def _docx_text(doc) -> str:
    """Body paragraphs plus table cells — many resumes are laid out in tables."""
    parts = [p.text for p in doc.paragraphs]
    for table in getattr(doc, "tables", []) or []:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text and c.text.strip()]
            if cells:
                parts.append(" | ".join(cells))
    return "\n".join(t.strip() for t in parts if t and t.strip())


def _extract_docx_bytes(content: bytes) -> str:
    try:
        import io

        from docx import Document  # type: ignore[import-untyped]

        return _docx_text(Document(io.BytesIO(content)))
    except Exception as e:
        logger.error("DOCX extraction failed: %s", e)
        return ""


def _extract_pdf_bytes(content: bytes) -> str:
    try:
        import fitz  # type: ignore[import-untyped]

        doc = fitz.open(stream=content, filetype="pdf")
        text = "\n".join(page.get_text() for page in doc)
        doc.close()
        return text
    except Exception as e:
        logger.error("PDF extraction failed: %s", e)
        return ""


def extract_text_from_bytes(content: bytes, filename: str = "") -> str:
    """Turn an uploaded file's bytes into plain text, dispatching on extension.

    Falls back to UTF-8 decoding for plain text (or unknown) uploads.
    """
    ext = Path(filename or "").suffix.lower()
    if ext in (".docx", ".doc"):
        return _extract_docx_bytes(content)
    if ext == ".pdf":
        return _extract_pdf_bytes(content)
    return content.decode("utf-8", errors="replace")


# ── Section Detection ─────────────────────────────────────────────────────────

_SECTION_PATTERNS: dict[str, re.Pattern] = {
    "summary": re.compile(
        r"^\s*(?:professional\s+)?summary|about\s+me|profile|overview|objective",
        re.IGNORECASE | re.MULTILINE,
    ),
    "experience": re.compile(
        r"^\s*(?:work\s+)?experience|employment|professional\s+experience|work\s+history",
        re.IGNORECASE | re.MULTILINE,
    ),
    "education": re.compile(
        r"^\s*education|academic|degree|university|college",
        re.IGNORECASE | re.MULTILINE,
    ),
    "skills": re.compile(
        r"^\s*(?:technical\s+)?skills?|competencies|technologies|tech\s+stack",
        re.IGNORECASE | re.MULTILINE,
    ),
    "projects": re.compile(
        r"^\s*(?:personal\s+)?projects?|portfolio|open[\s-]?source",
        re.IGNORECASE | re.MULTILINE,
    ),
    "certifications": re.compile(
        r"^\s*certifications?|licenses?|credentials",
        re.IGNORECASE | re.MULTILINE,
    ),
    "contact": re.compile(
        r"^\s*contact|contact\s+info",
        re.IGNORECASE | re.MULTILINE,
    ),
}


def _split_sections(text: str) -> dict[str, str]:
    """Split resume text into named sections."""
    lines = text.split("\n")
    section_starts: list[tuple[int, str]] = []

    for i, line in enumerate(lines):
        stripped = line.strip()
        if len(stripped) > 80:
            continue
        for name, pattern in _SECTION_PATTERNS.items():
            if pattern.match(stripped):
                section_starts.append((i, name))
                break

    sections: dict[str, str] = {}
    for idx, (start, name) in enumerate(section_starts):
        end = section_starts[idx + 1][0] if idx + 1 < len(section_starts) else len(lines)
        sections[name] = "\n".join(lines[start:end])

    return sections


# ── Contact Extraction ────────────────────────────────────────────────────────

def _extract_contact(text: str) -> ContactInfo:
    email_match = re.search(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", text)
    phone_match = re.search(r"(?:\+?\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4}", text)
    linkedin_match = re.search(r"linkedin\.com/in/[a-zA-Z0-9\-_%]+", text)
    github_match = re.search(r"github\.com/[a-zA-Z0-9\-_]+", text)
    website_match = re.search(r"(?:https?://)?(?:www\.)?[a-zA-Z0-9\-]+\.[a-zA-Z]{2,}(?:/[^\s]*)?", text)

    return ContactInfo(
        email=email_match.group() if email_match else "",
        phone=phone_match.group().strip() if phone_match else "",
        linkedin=f"https://{linkedin_match.group()}" if linkedin_match else "",
        github=f"https://{github_match.group()}" if github_match else "",
        website=website_match.group() if website_match else "",
    )


# ── Skill Extraction ──────────────────────────────────────────────────────────

def _extract_skills(text: str) -> list[Skill]:
    """Extract skills from resume text against the skills database."""
    text_lower = text.lower()
    found: list[Skill] = []
    seen: set[str] = set()

    for skill in SKILLS_DB:
        pattern = re.compile(r"\b" + re.escape(skill).replace(r"\ ", r"[\s\-_]?") + r"\b", re.IGNORECASE)
        if pattern.search(text_lower) and skill not in seen:
            seen.add(skill)
            cat = SkillCategory.technical
            if skill in {"leadership", "mentoring", "communication", "collaboration",
                         "problem solving", "critical thinking", "time management",
                         "project management", "stakeholder management", "technical writing",
                         "presentation", "public speaking", "requirements gathering",
                         "pair programming", "code review"}:
                cat = SkillCategory.soft
            found.append(Skill(name=skill, category=cat))

    return found


# ── Experience Parsing ────────────────────────────────────────────────────────

_DATE_RANGE_RE = re.compile(
    r"(\w{3,9})\s+(\d{4})\s*[-–—to]+\s*(?:(\w{3,9})\s+(\d{4})|present|current)",
    re.IGNORECASE,
)

_TITLE_COMPANY_PATTERNS = [
    re.compile(r"^(?P<title>.+?)\s*(?:at|@|,)\s*(?P<company>.+)$", re.IGNORECASE),
    re.compile(r"^(?P<company>.+?)\s*[-–—|]\s*(?P<title>.+)$", re.IGNORECASE),
]

_MONTH_MAP = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6,
    "jul": 7, "july": 7, "aug": 8, "august": 8, "sep": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}


def _parse_date(month_str: str, year_str: str) -> date | None:
    month = _MONTH_MAP.get(month_str.lower()[:3])
    if month is None:
        return None
    try:
        return date(int(year_str), month, 1)
    except (ValueError, TypeError):
        return None


def _parse_experiences(text: str) -> list[Experience]:
    """Parse experience entries from text."""
    experiences: list[Experience] = []
    blocks = re.split(r"\n{2,}", text)

    for block in blocks:
        lines = block.strip().split("\n")
        if not lines:
            continue

        date_match = _DATE_RANGE_RE.search(block)
        start_date: date | None = None
        end_date: date | None = None
        is_current = False

        if date_match:
            start_date = _parse_date(date_match.group(1), date_match.group(2))
            if date_match.group(3):
                end_date = _parse_date(date_match.group(3), date_match.group(4))
            else:
                is_current = True

        title = ""
        company = ""
        for line in lines[:3]:
            if date_match and (date_match.group(0) in line or len(line) > 100):
                continue
            for pat in _TITLE_COMPANY_PATTERNS:
                m = pat.match(line.strip())
                if m:
                    title = m.group("title").strip()
                    company = m.group("company").strip()
                    break
            if title:
                break

        if not title and lines:
            title = lines[0].strip()[:120]

        desc_lines = lines[3:] if len(lines) > 3 else lines[1:]
        description = "\n".join(desc_lines).strip()

        skills_in_desc = [s for s in _extract_skills(description) if s.name in SKILLS_DB][:10]

        if title:
            experiences.append(Experience(
                title=title,
                company=company,
                start_date=start_date or date(2020, 1, 1),
                end_date=end_date,
                description=description,
                skills_used=[s.name for s in skills_in_desc],
                is_current=is_current,
            ))

    return experiences


# ── Education Parsing ─────────────────────────────────────────────────────────

_DEGREE_RE = re.compile(
    r"(?:bachelor|master|ph\.?d\.?|doctorate|associate|b\.?s\.?|m\.?s\.?|b\.?a\.?|m\.?a\.?|b\.?e\.?|m\.?e\.?|b\.?tech|m\.?tech|mba|bca|mca|bcom|mcom)\s*(?:of|in|degree)?\s*[\w\s]*",
    re.IGNORECASE,
)
_GPA_RE = re.compile(r"(?:gpa|cgpa)[:\s]*(\d+\.\d+)", re.IGNORECASE)


def _parse_education(text: str) -> list[Education]:
    entries: list[Education] = []
    blocks = re.split(r"\n{2,}", text)

    for block in blocks:
        degree = ""
        degree_match = _DEGREE_RE.search(block)
        if degree_match:
            degree = degree_match.group().strip()

        institution = ""
        for line in block.split("\n"):
            line_s = line.strip()
            if line_s and not _DEGREE_RE.match(line_s) and not _DATE_RANGE_RE.search(line_s):
                if len(line_s) > 3:
                    institution = line_s
                    break

        dates = _DATE_RANGE_RE.search(block)
        start_date = _parse_date(dates.group(1), dates.group(2)) if dates else None
        end_date = _parse_date(dates.group(3), dates.group(4)) if dates and dates.group(3) else start_date

        gpa = None
        gpa_match = _GPA_RE.search(block)
        if gpa_match:
            try:
                gpa = float(gpa_match.group(1))
            except ValueError:
                pass

        if institution or degree:
            entries.append(Education(
                institution=institution,
                degree=degree,
                field=degree,
                start_date=start_date,
                end_date=end_date,
                gpa=gpa,
            ))

    return entries


# ── Project Parsing ───────────────────────────────────────────────────────────

def _parse_projects(text: str) -> list[Project]:
    projects: list[Project] = []
    blocks = re.split(r"\n{2,}", text)

    for block in blocks:
        lines = block.strip().split("\n")
        if not lines:
            continue
        name = lines[0].strip()[:120]
        description = "\n".join(lines[1:]).strip()
        techs = [s.name for s in _extract_skills(block)]

        if name:
            projects.append(Project(name=name, description=description, technologies=techs))

    return projects


# ── Certification Parsing ─────────────────────────────────────────────────────

def _parse_certifications(text: str) -> list[Certification]:
    certs: list[Certification] = []
    for line in text.split("\n"):
        line_s = line.strip()
        if line_s:
            certs.append(Certification(name=line_s))
    return certs


# ── Public API ────────────────────────────────────────────────────────────────

_parse_cache: dict[str, ResumeProfile] = {}


def _build_profile(text: str) -> ResumeProfile:
    """Build a ResumeProfile from already-extracted raw text."""
    text = _clean_text(text)
    sections = _split_sections(text)

    contact = _extract_contact(text)
    skills = _extract_skills(text)
    summary = ""
    if "summary" in sections:
        summary = re.sub(r"^\s*(?:professional\s+)?summary\s*:?\s*", "", sections["summary"], flags=re.IGNORECASE).strip()

    experiences = _parse_experiences(sections.get("experience", ""))
    education = _parse_education(sections.get("education", ""))
    projects = _parse_projects(sections.get("projects", ""))
    certifications = _parse_certifications(sections.get("certifications", ""))

    years = 0.0
    if experiences:
        earliest = min(e.start_date for e in experiences)
        latest_end = max((e.end_date or date.today() for e in experiences), default=date.today())
        years = round((latest_end - earliest).days / 365.25, 1)

    return ResumeProfile(
        skills=skills,
        experience=experiences,
        education=education,
        projects=projects,
        certifications=certifications,
        years_experience=years,
        summary=summary,
        contact_info=contact,
    )


def parse_resume_from_text(raw_text: str, *, content_hash: str = "") -> ResumeProfile:
    """Parse a resume from raw text (e.g. already stored in DB)."""
    if content_hash and content_hash in _parse_cache:
        return _parse_cache[content_hash]

    profile = _build_profile(raw_text)

    if content_hash:
        _parse_cache[content_hash] = profile
    return profile
