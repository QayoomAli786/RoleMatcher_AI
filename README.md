<div align="center">

<img src="https://img.shields.io/badge/Status-Active-brightgreen?style=for-the-badge&logo=amazonwebservices" alt="Active"/>
<img src="https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python"/>
<img src="https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI"/>
<img src="https://img.shields.io/badge/LangGraph-Workflows-FF6B6B?style=for-the-badge" alt="LangGraph"/>
<img src="https://img.shields.io/badge/LangChain-Integration-3776AB?style=for-the-badge" alt="LangChain"/>

<br/>
<br/>

<pre>
███████╗  ██████╗ ██╗     ███████╗███╗   ███╗ █████╗ ████████╗ ██████╗██╗  ██╗███████╗██████╗  █████╗ ██╗
██╔══██╗██╔═══██╗██║     ██╔════╝████╗ ████║██╔══██╗╚══██╔══╝██╔════╝██║  ██║██╔════╝██╔══██╗██╔══██╗██║
██████╔╝██║   ██║██║     █████╗  ██╔████╔██║███████║   ██║   ██║     ███████║█████╗  ██████╔╝███████║██║
██╔══██╗██║   ██║██║     ██╔══╝  ██║╚██╔╝██║██╔══██║   ██║   ██║     ██╔══██║██╔══╝  ██╔══██╗██╔══██║██║
██║  ██║╚██████╔╝███████╗███████╗██║ ╚═╝ ██║██║  ██║   ██║   ╚██████╗██║  ██║███████╗██║  ██║██║  ██║██║
╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚══════╝╚═╝     ╚═╝╚═╝  ╚═╝   ╚═╝    ╚═════╝╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝
</pre>

### An AI-powered platform for intelligent job-role matching, resume analysis, ATS optimization, and career guidance.

*Stop applying blindly. Start landing interviews.*

</div>
---

## Overview

**RoleMatcher AI** is a multi-workflow AI system that automates every stage of the modern job search. Built on **LangGraph** and **LangChain**, it runs eight specialized workflows — **Resume Parser**, **Job Matcher**, **ATS Analyzer**, **Career Strategist**, **Interview Coach**, **Cover Letter**, **Resume Optimizer**, and **Chat Assistant** — that collaborate through shared state to source relevant roles, optimize your resume, and produce a personalized career roadmap.

Users bring their own API key (Gemini, OpenAI, Groq, DeepSeek, or Qwen) through the Settings panel — no server-side key is required.

> **No more spray-and-pray applications. Just targeted, data-driven career moves.**

---

## Features

| Feature | Description |
|---|---|
| **Resume Parsing** | PDF upload in the UI (PDF/DOCX/TXT via API) into a structured profile with skill detection |
| **Multi-Source Job Discovery** | Aggregates listings from LinkedIn, RemoteOK, and Adzuna with cross-source deduplication |
| **Skill-Based Job Matching** | Multi-factor scoring: skill overlap, experience, seniority, location, salary, and semantic similarity |
| **ATS Compatibility Scoring** | Keyword coverage, skill gaps, experience alignment, and LLM-powered recommendations |
| **AI Resume Builder** | Rewrites your resume for one specific job — keyword injection, guarded against fabricated content, exportable as DOCX or PDF |
| **Strategic Career Planning** | Skill-gap analysis, market intelligence, step-by-step learning roadmap, portfolio projects, and action plans |
| **Interview Preparation** | Question generation with 0–10 answer evaluation, strengths/improvements, model answers, weak-question retry |
| **Cover Letter Generation** | Tailored cover letters with tone selection (professional, enthusiastic, confident, creative) and session history |
| **PDF Exports** | Client-side PDF export of career plans and interview reports (vendored jsPDF) |
| **AI Chat Assistant** | Context-aware coaching with conversation history and tool usage tracking |
| **Model Settings** | Bring your own key and choose the model in the UI — Gemini, OpenAI, DeepSeek, Qwen, or Groq |
| **Premium UI** | Glassmorphism design with animated workflow canvas, particles, micro-animations, and a dark-mode aesthetic |

> **Note:** Application tracking (`/api/applications`) and the dedicated `/api/ats/*` routes are API-only in this release — the UI runs ATS analysis per job via **Jobs → ATS**.

---

## Documentation

📖 **[DOCUMENTATION.md](DOCUMENTATION.md)** — the complete reference explaining **every feature, screen, and button**: what each control does, which API call it triggers, how each backend workflow operates, the full endpoint list, and troubleshooting.

---

## Tech Stack

### Backend — AI and Logic

- **Framework**: [FastAPI](https://fastapi.tiangolo.com/) (Python 3.11+)
- **AI Orchestration**: [LangGraph](https://langchain-ai.github.io/langgraph/) — stateful graph workflows
- **LLM Integration**: [LangChain](https://www.langchain.com/) — `ChatGoogleGenerativeAI`, `ChatOpenAI`, and `ChatGroq` with per-provider model routing
- **Store**: In-memory stores (demo mode — no database required)
- **Auth**: Single guest session; per-request `X-API-Key` and `X-Model` headers supply the LLM credentials
- **Resume Parsing**: PyMuPDF, python-docx
- **Job Sources**: HTTPX, BeautifulSoup4 (LinkedIn, Adzuna, RemoteOK)
- **Similarity**: NumPy (TF-IDF embeddings)

### Frontend — UI/UX

- **Logic**: Vanilla JavaScript with async/await API integration
- **Styling**: Custom CSS design system — glassmorphism, micro-animations, backdrop filters, particles, dark mode
- **Markdown**: marked.js for career plan and feedback rendering
- **Export**: Vendored jsPDF for client-side PDF export

---

## Project Architecture

```
RoleMatcher_AI/
│
├── backend/                        # FastAPI + LangGraph backend
│   ├── main.py                     # App entry point, CORS, middleware, static frontend
│   ├── core/
│   │   ├── config.py               # Pydantic settings (CC_* env vars)
│   │   ├── schemas.py              # Request/response models
│   │   ├── state.py                # LangGraph TypedDict state definitions
│   │   └── store.py                # In-memory data store
│   │
│   ├── graphs/                     # LangGraph workflow definitions
│   │   ├── job_graph.py            # Job discovery & matching workflow
│   │   ├── ats_graph.py            # ATS scoring workflow
│   │   ├── career_graph.py         # Career planning workflow
│   │   ├── cover_letter_graph.py   # Cover letter generation workflow
│   │   ├── resume_optimizer_graph.py # Resume tailoring workflow
│   │   └── chat_graph.py           # Conversational AI workflow
│   │
│   ├── services/                   # Deterministic and LLM-powered services
│   │   ├── resume_parser.py        # PDF/DOCX -> structured profile
│   │   ├── job_normalizer.py       # Raw job data normalization
│   │   ├── job_deduplicator.py     # Cross-source deduplication
│   │   ├── skill_aliases.py        # Skill name normalization
│   │   ├── skill_gap_engine.py     # Gap analysis & learning paths
│   │   ├── ats_engine.py           # Deterministic ATS scoring
│   │   ├── market_analyzer.py      # Market intelligence aggregation
│   │   ├── embeddings.py           # Vector embedding service
│   │   ├── llm_service.py          # Model factory, routing & metrics
│   │   ├── docx_builder.py         # DOCX export for tailored resumes
│   │   └── job_sources/            # Job board integrations
│   │       ├── base.py             # Abstract source interface
│   │       ├── linkedin.py         # LinkedIn Guest API
│   │       ├── adzuna.py           # Adzuna API
│   │       ├── remoteok.py         # RemoteOK API
│   │       └── manager.py          # Source orchestrator
│   │
│   ├── api/                        # FastAPI route handlers
│   │   ├── router.py               # Central router (aggregates sub-routers)
│   │   ├── resume.py               # Resume upload & parsing
│   │   ├── resume_optimizer.py     # Resume tailoring & DOCX download
│   │   ├── jobs.py                 # Job search, matching, ATS analysis
│   │   ├── ats.py                  # ATS endpoints (stubs in in-memory mode)
│   │   ├── career.py               # Career planning
│   │   ├── interview.py            # Interview preparation
│   │   ├── cover_letter.py         # Cover letter generation
│   │   ├── chat.py                 # Chat assistant & conversations
│   │   ├── reviews.py              # User reviews
│   │   ├── applications.py         # Application tracking (API only)
│   │   ├── auth.py                 # Guest user profile
│   │   └── admin.py                # Health check & system stats
│   │
│   ├── security/                   # Auth, rate limiting, input sanitization
│   ├── observability/              # Request tracing & metrics
│   └── tests/                      # Self-check test modules
│
├── frontend/                       # Static web interface
│   ├── index.html                  # Glassmorphic UI shell
│   ├── script.js                   # API integration & state management
│   ├── style.css                   # Theme, animations & CSS variables
│   ├── workflow.js                 # Workflow visualization
│   ├── vendor/                     # Vendored frontend libraries (jsPDF)
│   └── logo.png
│
├── .env.example                    # Environment variable template
├── requirements.txt                # Python dependencies
├── README.md
└── DOCUMENTATION.md                # Complete feature & button reference
```

---

## How It Works

<table>
<tr>
<td width="33%" align="center">
<h3>Resume Parser</h3>
<p>Extracts structured profiles from PDF/DOCX. Detects skills, experience, education, and certifications.</p>
</td>
<td width="33%" align="center">
<h3>Job Matcher</h3>
<p>Aggregates from LinkedIn, RemoteOK, and Adzuna. Normalizes, deduplicates, and scores matches using skill overlap and semantic similarity.</p>
</td>
<td width="33%" align="center">
<h3>ATS Analyzer</h3>
<p>Deterministic keyword/skill/education scoring plus LLM-powered explanations and recommendations.</p>
</td>
</tr>
<tr>
<td width="33%" align="center">
<h3>Career Strategist</h3>
<p>Identifies skill gaps against market demand, then generates learning plans, project suggestions, and application strategies.</p>
</td>
<td width="33%" align="center">
<h3>Interview Coach</h3>
<p>Generates targeted questions (technical, behavioral, or mixed) and evaluates answers 0–10 with feedback, model answers, and weak-question retry.</p>
</td>
<td width="33%" align="center">
<h3>Chat Assistant</h3>
<p>Context-aware career coaching with tool usage. Answers questions about your resume, jobs, ATS scores, and career plans.</p>
</td>
</tr>
<tr>
<td width="33%" align="center">
<h3>Cover Letter</h3>
<p>Tailored letters from your resume or manual details, with four selectable tones and a per-session history.</p>
</td>
<td width="33%" align="center">
<h3>Resume Optimizer</h3>
<p>Rewrites your resume for one specific job with keyword injection and anti-fabrication guardrails; exports to DOCX or PDF.</p>
</td>
<td width="33%" align="center">
</td>
</tr>
</table>

---

## Getting Started

### Prerequisites

- Python **3.11+**
- An LLM API key (Gemini, OpenAI, Groq, DeepSeek, or Qwen)

### 1. Clone and Install

```bash
git clone https://github.com/QayoomAli786/RoleMatcher_AI.git
cd RoleMatcher_AI

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

### 2. Configure (Optional)

```bash
cp .env.example .env
```

The application starts without a `.env` file. All variables are optional and use the `CC_` prefix:

| Variable | Purpose |
|---|---|
| `CC_GEMINI_API_KEY`, `CC_OPENAI_API_KEY`, `CC_GROQ_API_KEY`, `CC_DEEPSEEK_API_KEY`, `CC_QWEN_API_KEY` | Optional server-side LLM keys; users can always supply their own in Settings |
| `CC_FAST_MODEL` / `CC_STRONG_MODEL` | Model routing for fast and strong tiers |
| `CC_REDIS_URL` | Redis-backed rate limiting; falls back to an in-memory limiter when unset or unreachable |
| `CC_DEBUG` | Debug logging (default: `false`) |

### 3. Run

Run from the repository root so the `backend` package is importable:

```bash
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

- **Application**: [http://localhost:8000](http://localhost:8000) — configure your API key and model in **Settings**
- **Interactive API docs**: [http://localhost:8000/docs](http://localhost:8000/docs)

### 4. Run the Tests

Each test module is self-checking — run any of them directly:

```bash
python -m backend.tests.test_skill_aliases
python -m backend.tests.test_interview_parse
python -m backend.tests.test_interview_review
python -m backend.tests.test_job_filters
python -m backend.tests.test_career_input
python -m backend.tests.test_career_tool_loop
python -m backend.tests.test_docx_builder
```

## API Overview

All endpoints are prefixed with `/api`. Two optional headers are recognized on every request:

| Header | Purpose |
|---|---|
| `X-API-Key` | LLM credential used for this request instead of a server-side key |
| `X-Model` | Forces a specific model (for example `openai/gpt-4o-mini`), overriding the fast/strong tier |

| Endpoint | Method | Description |
|---|---|---|
| `/api/health` | `GET` | Service health and version |
| `/api/auth/me` | `GET` | Current guest user profile |
| `/api/resumes` | `POST` / `GET` | Upload and parse a resume (PDF/DOCX/TXT); list parsed resumes |
| `/api/resumes/{id}` | `GET` / `DELETE` | Fetch or delete a parsed resume |
| `/api/resume-optimizer/tailor` | `POST` | Tailor a resume to a target job description |
| `/api/resume-optimizer/{id}/download` | `GET` | Download the tailored resume as DOCX |
| `/api/jobs/search` | `POST` | Search jobs by keywords, target role, location, or resume |
| `/api/jobs/{id}/analyze` | `POST` | Run ATS analysis against a job |
| `/api/career/plan` | `POST` / `GET` | Generate and list career plans |
| `/api/career/market` | `GET` | Market intelligence for target roles |
| `/api/career/skill-gaps` | `GET` | Skill gap analysis against market demand |
| `/api/interviews` | `POST` | Start an interview session |
| `/api/interviews/{id}` | `GET` | Fetch interview session results |
| `/api/interviews/{id}/answer` | `POST` | Submit an answer for evaluation |
| `/api/interviews/{id}/feedback` | `GET` | Retrieve interview feedback |
| `/api/cover-letters` | `POST` / `GET` | Generate and list cover letters |
| `/api/cover-letters/{id}` | `GET` | Fetch one cover letter |
| `/api/chat` | `POST` | Send a message to the AI assistant |
| `/api/conversations` | `GET` | List chat conversations |
| `/api/conversations/{id}` | `GET` / `DELETE` | Fetch or delete a conversation |
| `/api/applications` | `POST` / `GET` | Track and list job applications |
| `/api/applications/{id}` | `PATCH` | Update an application's status |
| `/api/applications/analytics` | `GET` | Application statistics |
| `/api/reviews` | `POST` / `GET` | Submit or list user reviews |
| `/api/admin/stats` | `GET` | Runtime statistics |
| `/api/admin/refresh-jobs` | `POST` | Force-refresh the job cache |
| `/docs` | `GET` | Interactive Swagger UI (served at the site root) |

> The full endpoint list (including resume-optimizer listing and ATS stubs) is documented in **[DOCUMENTATION.md](DOCUMENTATION.md#14-complete-api-reference)**.

Requests are rate-limited per IP (60 requests per minute by default); rejected requests return `429` with `X-RateLimit-*` headers.

> **Note:** The dedicated `/api/ats/*` routes are placeholders. ATS analysis is fully available via [`/api/jobs/{id}/analyze`](#api-overview), which invokes the same `ats_graph` pipeline.

---

## Roadmap

- [x] Resume parsing with skill detection
- [x] Multi-source job aggregation (LinkedIn, RemoteOK, Adzuna)
- [x] Skill-based job matching with scoring
- [x] ATS compatibility analysis
- [x] Career planning with skill gap analysis
- [x] Interview preparation with answer evaluation
- [x] Cover letter generation with tone selection
- [x] Resume tailoring with DOCX export
- [x] Conversational AI chat assistant
- [x] User-configurable model and API key (bring your own key)
- [x] Client-side PDF exports (career plan, interview report, tailored resume)
- [ ] Application tracking UI (API already available)
- [ ] Persistent storage (SQLite/Postgres) behind the existing store interface

---

<div align="center">

Built by **Qayoom Ali**

*If RoleMatcher helped you land a role, consider giving this repo a star — it means the world!*

</div>
