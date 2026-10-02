<div align="center">

<img src="https://img.shields.io/badge/Status-Active-brightgreen?style=for-the-badge&logo=amazonwebservices" alt="Active"/>
<img src="https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python"/>
<img src="https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI"/>
<img src="https://img.shields.io/badge/LangGraph-Workflows-FF6B6B?style=for-the-badge" alt="LangGraph"/>
<img src="https://img.shields.io/badge/LangChain-Integration-3776AB?style=for-the-badge" alt="LangChain"/>
<img src="https://img.shields.io/badge/Docker-Ready-2496ED?style=for-the-badge&logo=docker&logoColor=white" alt="Docker"/>

<br/>
<br/>
███████╗  ██████╗ ██╗     ███████╗███╗   ███╗ █████╗ ████████╗ ██████╗██╗  ██╗███████╗██████╗  █████╗ ██╗
██╔══██╗██╔═══██╗██║     ██╔════╝████╗ ████║██╔══██╗╚══██╔══╝██╔════╝██║  ██║██╔════╝██╔══██╗██╔══██╗██║
██████╔╝██║   ██║██║     █████╗  ██╔████╔██║███████║   ██║   ██║     ███████║█████╗  ██████╔╝███████║██║
██╔══██╗██║   ██║██║     ██╔══╝  ██║╚██╔╝██║██╔══██║   ██║   ██║     ██╔══██║██╔══╝  ██╔══██╗██╔══██║██║
██║  ██║╚██████╔╝███████╗███████╗██║ ╚═╝ ██║██║  ██║   ██║   ╚██████╗██║  ██║███████╗██║  ██║██║  ██║██║
╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚══════╝╚═╝     ╚═╝╚═╝  ╚═╝   ╚═╝    ╚═════╝╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝

### An AI-powered platform for intelligent job-role matching, resume analysis, ATS optimization, and career guidance.

*Stop applying blindly. Start landing interviews.*

<br/>

[![Live Demo](https://img.shields.io/badge/Live%20Demo-54.206.89.234-6366F1?style=for-the-badge)](http://54.206.89.234:8000/)

</div>

---

## Overview

**CareerCopilot AI** is a multi-workflow AI system that automates every stage of the modern job search. Built on **LangGraph** and **LangChain**, it deploys six specialized workflows — **Resume Parser**, **Job Matcher**, **ATS Analyzer**, **Career Strategist**, **Interview Coach**, and **Chat Assistant** — that work together through shared state to find your dream roles, optimize your resume, and build a personalized career roadmap.

Users bring their own API key (Gemini, OpenAI, Groq, DeepSeek, or Qwen) via the Settings panel — no server-side keys required.

> **No more spray-and-pray applications. Just targeted, data-driven career moves.**

---

## Features

| Feature | Description |
|---|---|
| **Resume Parsing** | PDF/DOCX extraction into structured profiles with skill detection |
| **Multi-Source Job Discovery** | Aggregates listings from LinkedIn, RemoteOK, and Adzuna with deduplication |
| **Skill-Based Job Matching** | Multi-factor scoring: skill overlap, experience, seniority, location, salary, and semantic similarity |
| **ATS Compatibility Scoring** | Keyword coverage, skill gaps, experience alignment, and LLM-powered recommendations |
| **Strategic Career Planning** | Skill gap analysis, market intelligence, learning roadmaps, and action plans |
| **Interview Preparation** | Question generation with answer evaluation across technical, behavioral, and system design categories |
| **Cover Letter Generation** | Tailored cover letters with tone selection (professional, enthusiastic, confident, creative) |
| **AI Chat Assistant** | Context-aware coaching with conversation history and tool usage tracking |
| **Model Settings** | Choose your AI provider and model from the UI — Gemini, OpenAI, DeepSeek, Qwen, Groq — with per-user API key |
| **Premium UI** | Glassmorphism design with dynamic particles, micro-animations, and dark-mode aesthetic |

---

## Tech Stack

### Backend — AI & Logic
- **Framework**: [FastAPI](https://fastapi.tiangolo.com/) (Python 3.11+)
- **AI Orchestration**: [LangGraph](https://langchain-ai.github.io/langgraph/) — stateful graph workflows
- **LLM Integration**: [LangChain](https://www.langchain.com/) — `ChatGoogleGenerativeAI`, `ChatOpenAI`, `ChatGroq` for per-provider model routing
- **Store**: In-memory stores (guest-user demo; no database layer)
- **Auth**: Guest user auth with `X-API-Key` / `X-Model` per-request headers
- **Resume Parsing**: PyMuPDF, python-docx
- **Scraping**: HTTPX, BeautifulSoup4
- **Numerics**: NumPy (TF-IDF embeddings, similarity)

### Frontend — UI/UX
- **Styling**: Custom CSS with glassmorphism design system
- **Logic**: Vanilla JavaScript (Async/Await API integration)
- **Markdown**: marked.js for career plan rendering
- **Aesthetics**: Glassmorphism, micro-animations, backdrop filters, particle effects

### DevOps & Infrastructure
- **Hosting**: [AWS EC2](https://aws.amazon.com/ec2/) — Docker container on Ubuntu 24.04
- **Containerization**: [Docker](https://www.docker.com/) — multi-stage build, non-root user
- **Dependency Management**: pip + uv

---

## Project Architecture

```
CareerCopilot_AI/
│
├── backend/                     # FastAPI + LangGraph Backend
│   ├── main.py                  # App entrypoint, CORS, static files, middleware
│   ├── core/
│   │   ├── config.py            # Pydantic settings (env-driven)
│   │   ├── schemas.py           # Pydantic request/response schemas
│   │   ├── state.py             # LangGraph TypedDict state definitions
│   │   └── store.py             # In-memory data store
│   │
│   ├── graphs/                  # LangGraph workflow definitions
│   │   ├── job_graph.py         # Job discovery & matching workflow
│   │   ├── ats_graph.py         # ATS scoring workflow
│   │   ├── career_graph.py      # Career planning workflow
│   │   ├── cover_letter_graph.py# Cover letter generation workflow
│   │   ├── resume_optimizer_graph.py # Resume tailoring workflow
│   │   └── chat_graph.py        # Conversational AI workflow
│   │
│   ├── services/                # Deterministic & LLM-powered services
│   │   ├── resume_parser.py     # PDF/DOCX -> structured profile
│   │   ├── job_normalizer.py    # Raw job data normalization
│   │   ├── job_deduplicator.py  # Cross-source deduplication
│   │   ├── skill_aliases.py     # Skill name normalization
│   │   ├── skill_gap_engine.py  # Gap analysis & learning paths
│   │   ├── ats_engine.py        # Deterministic ATS scoring
│   │   ├── market_analyzer.py   # Market intelligence aggregation
│   │   ├── embeddings.py        # Vector embedding service
│   │   ├── llm_service.py       # LangChain model factory, routing & metrics
│   │   └── job_sources/         # Job board integrations
│   │       ├── base.py          # Abstract source interface
│   │       ├── linkedin.py      # LinkedIn Guest API
│   │       ├── adzuna.py        # Adzuna API
│   │       ├── remoteok.py      # RemoteOK API
│   │       └── manager.py       # Source orchestrator
│   │
│   ├── api/                     # FastAPI route handlers
│   │   ├── router.py            # Central router (aggregates sub-routers)
│   │   ├── resume.py            # Resume upload & parsing endpoints
│   │   ├── jobs.py              # Job search, match, and ATS analysis endpoints
│   │   ├── ats.py               # ATS endpoints (placeholder; analysis runs via jobs.py)
│   │   ├── career.py            # Career planning endpoints
│   │   ├── interview.py         # Interview prep endpoints
│   │   ├── cover_letter.py      # Cover letter generation endpoints
│   │   ├── chat.py              # Chat assistant endpoints
│   │   ├── reviews.py           # User review endpoints
│   │   ├── applications.py      # Application tracking endpoints
│   │   ├── auth.py              # Auth endpoints
│   │   └── admin.py             # Admin & health check endpoints
│   │
│   ├── security/                # Auth & rate limiting
│   │   ├── auth.py              # Guest user auth
│   │   ├── rate_limit.py        # Per-IP rate limiting
│   │   └── sanitization.py      # Input sanitization
│   │
│   ├── observability/           # Monitoring & tracing
│   │   ├── tracing.py           # Request tracing middleware
│   │   └── metrics.py           # In-memory metrics collector
│
├── frontend/                    # Static Web Interface
│   ├── index.html               # Glassmorphic UI shell
│   ├── script.js                # API integration & state management
│   ├── style.css                # Custom animations, variables & theme
│   ├── workflow.js              # Workflow visualization
│   └── logo.png                 # App logo
│
├── tests/                       # Test suite
│   ├── unit/                    # Unit tests (ats_engine, job_deduplicator, etc.)
│   ├── integration/             # API integration tests
│   ├── graph/                   # LangGraph workflow tests
│   ├── security/                # Security/sanitization tests
│   └── evaluation/              # (placeholder)
│
├── Dockerfile                   # Multi-stage Docker build
├── docker-compose.yml           # Docker Compose config
├── .dockerignore                # Docker build exclusions
├── conftest.py                  # Pytest fixtures
├── .env.example                 # Environment variable template
├── pyproject.toml               # Project metadata & tool config
├── requirements.txt             # Python dependencies
└── README.md
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
<p>Identifies skill gaps against market demand, generates learning plans, project suggestions, and application strategies.</p>
</td>
<td width="33%" align="center">
<h3>Interview Coach</h3>
<p>Generates targeted questions (technical, behavioral, system design) and evaluates answers with detailed feedback.</p>
</td>
<td width="33%" align="center">
<h3>Chat Assistant</h3>
<p>Context-aware career coaching with tool usage. Answers questions about resume, jobs, ATS scores, and career plans.</p>
</td>
</tr>
</table>

---

## Getting Started

### Prerequisites
- Python **3.11+**
- **Docker** (recommended) or pip

### Option 1 — Docker (Recommended)

```bash
git clone https://github.com/Dev-with-Mouzan/CareerCopilot_AI.git
cd CareerCopilot_AI
docker build -t career-copilot .
docker run -d -p 8000:8000 --name career-copilot -v $(pwd)/data:/app/data career-copilot
```

Open `http://localhost:8000` — configure your API key and model in Settings.

### Option 2 — Local Development

```bash
git clone https://github.com/Dev-with-Mouzan/CareerCopilot_AI.git
cd CareerCopilot_AI
pip install -r requirements.txt
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000` in your browser.

**API docs:** `http://localhost:8000/docs`

---

## API Overview

All endpoints are prefixed with `/api`. The optional per-user API key and model are sent via `X-API-Key` and `X-Model` headers.

| Endpoint | Method | Description |
|---|---|---|
| `/api/resumes` | `POST` | Upload and parse a resume (PDF/DOCX) |
| `/api/resumes/{id}` | `GET` / `DELETE` | Fetch or delete a parsed resume |
| `/api/jobs/search` | `POST` | Search jobs by keywords or resume |
| `/api/jobs/{id}/analyze` | `POST` | Run ATS analysis against a job |
| `/api/career/plan` | `POST` | Generate a career plan |
| `/api/career/market` | `GET` | Market intelligence for target roles |
| `/api/career/skill-gaps` | `GET` | Skill gap analysis vs. market demand |
| `/api/interviews` | `POST` | Start an interview session |
| `/api/interviews/{id}/answer` | `POST` | Submit an answer for evaluation |
| `/api/cover-letters` | `POST` | Generate a tailored cover letter |
| `/api/chat` | `POST` | Send a message to the AI assistant |
| `/api/applications` | `POST` / `GET` | Track and list job applications |
| `/api/reviews` | `GET` / `POST` | List or submit user reviews |
| `/api/docs` | `GET` | Interactive Swagger API documentation |

> **Note:** The dedicated `/api/ats/*` routes are currently placeholders. ATS analysis is fully available via [`/api/jobs/{job_id}/analyze`](#api-overview), which invokes the same `ats_graph` pipeline.

---

## Deployment

| Layer | Platform | Purpose |
|---|---|---|
| **Full Stack** | [AWS EC2](https://aws.amazon.com/ec2/) | Docker container running FastAPI + static frontend |

**Live Application: [http://54.206.89.234:8000/](http://54.206.89.234:8000/)**

### Deploy on AWS EC2

```bash
# 1. Install Docker on Ubuntu 24.04
sudo apt update && sudo apt install -y git docker.io
sudo systemctl start docker && sudo systemctl enable docker
sudo usermod -aG docker ubuntu
newgrp docker

# 2. Clone and build
git clone https://github.com/Dev-with-Mouzan/CareerCopilot_AI.git
cd CareerCopilot_AI
docker build -t career-copilot .

# 3. Run
docker run -d -p 8000:8000 --name career-copilot \
  -v $(pwd)/data:/app/data \
  career-copilot
```

> **Note:** Open port 8000 in your EC2 Security Group. Users must configure their own API key and model in Settings before using the app.

---

## Roadmap

- [x] Resume parsing with skill detection
- [x] Multi-source job aggregation (LinkedIn, RemoteOK, Adzuna)
- [x] Skill-based job matching with scoring
- [x] ATS compatibility analysis
- [x] Career planning with skill gap analysis
- [x] Interview preparation with answer evaluation
- [x] Cover letter generation with tone selection
- [x] Conversational AI chat assistant
- [x] User-configurable model and API key (bring your own key)
- [x] Docker deployment on AWS EC2
- [x] Multi-language resume support

---

## Contributing

Contributions are welcome! Please open an issue first to discuss what you'd like to change, then submit a pull request.

1. Fork the repository
2. Create your feature branch: `git checkout -b feature/your-feature`
3. Commit your changes: `git commit -m 'Add your feature'`
4. Push to the branch: `git push origin feature/your-feature`
5. Open a Pull Request

---

<div align="center">

Built by **Mouzan Raza**

*If CareerCopilot helped you land a role, consider giving this repo a star — it means the world!*

[![Live Demo](https://img.shields.io/badge/Try%20It%20Now-54.206.89.234-6366F1?style=for-the-badge)](http://54.206.89.234:8000/)

</div>
