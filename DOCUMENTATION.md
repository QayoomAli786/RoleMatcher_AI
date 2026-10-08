# RoleMatcher AI — Complete Documentation

**Every feature, every button, every screen — explained.**

This is the full reference for the RoleMatcher AI web application. It covers what each
section does, what every button and input does when you click it, which API call it
triggers, and how the backend features work behind the scenes.

> **Before anything works:** the app requires an API key. On first launch you will see an
> **API Key Required** overlay. Open **Settings**, pick a provider (Google Gemini, OpenAI,
> Groq, DeepSeek, or Qwen), pick a model, paste your key, and press **Save Model Settings**.
> Your key is stored in the browser (`localStorage`) and sent with every request as the
> `X-API-Key` header — no server-side key is needed.

---

## Table of Contents

1. [Global Interface Elements](#1-global-interface-elements)
2. [Home / Dashboard](#2-home--dashboard)
3. [Resume](#3-resume)
4. [Jobs](#4-jobs)
5. [ATS Analysis Modal](#5-ats-analysis-modal)
6. [AI Resume Builder Modal](#6-ai-resume-builder-modal)
7. [Career Plan](#7-career-plan)
8. [Interview Prep](#8-interview-prep)
9. [Cover Letter](#9-cover-letter)
10. [Reviews](#10-reviews)
11. [Settings](#11-settings)
12. [AI Career Coach (Chat)](#12-ai-career-coach-chat)
13. [How the Backend Features Work](#13-how-the-backend-features-work)
14. [Complete API Reference](#14-complete-api-reference)
15. [Troubleshooting](#15-troubleshooting)

---

## 1. Global Interface Elements

These appear on every screen.

| Element | Location | What it does |
|---|---|---|
| **Logo** (`RoleMatcherAI`) | Top-left | Brand mark. Clicking does nothing (visual only). |
| **Nav links**: Home, Resume, Jobs, Career, Interview, Cover Letter, Reviews | Top center | Switches the active section. If no API key is configured, any link except Settings redirects you to Settings and shows the API Key overlay. Active link is highlighted. |
| **Hamburger menu** ☰ | Top-right (mobile) | Opens/closes the nav links on small screens. |
| **Settings cog** ⚙ | Top-right | Navigates to the Settings section. |
| **Page loader** | Full screen on launch | Logo + progress bar shown for ~1.4 s while the page initializes, then fades out. |
| **API Key Required overlay** | Full screen | Blocks the app until you configure a provider, model, and key. Its **Open Settings** button jumps to the Settings section. |
| **Toast notifications** | Bottom corner | Pop up for every success/error/info event (e.g. "Resume uploaded successfully"). Auto-dismiss after 3.5 s. |
| **Loading overlay** | Full screen | Spinner + status text ("Searching jobs…", "Generating career plan…") shown during any API call, hidden when it finishes. |
| **Floating chat button** 💬 | Bottom-right | Opens/closes the AI Career Coach chat widget (see [§12](#12-ai-career-coach-chat)). |
| **Workflow canvas + ambient blobs** | Background | Animated background: a moving node-graph canvas (`workflow.js`) plus soft floating blobs — pure decoration, no interaction. |

**API-key gating rule:** `navigateTo()` checks `isApiKeyConfigured()` (both `aiApiKey`
and `aiModel` present in `localStorage`). If not set, you get an error toast, the API Key
overlay appears, and you are forced to the Settings section. Only Settings is reachable
without a key.

---

## 2. Home / Dashboard

The landing screen (`section-dashboard`) — marketing hero, progress tracking, and shortcuts.

### Hero area

| Control | What it does |
|---|---|
| **Get Started Free** (rocket icon) | Navigates to the **Resume** section to upload your resume. |
| **Browse Jobs** (search icon) | Navigates to the **Jobs** section. |
| Hero pills ("AI Resume Builder", "Automated Job Tracking", "ATS Score Analysis", "AI Interview Prep") | Static feature badges — not clickable. |
| Badge "Trusted by thousands of job seekers", avatars, "4.9/5 from 2,400+ users" | Static social proof — not clickable. |
| Logo marquee (Google, Microsoft, Amazon…) | Auto-scrolling brand strip — decorative only. |

### Stats cards

Four cards: **Resumes Analyzed**, **Jobs Matched**, **Avg ATS Score**, **Active Users**.
These show static demo numbers — they are display-only (the chevron arrow is decorative).

### How It Works

Four static steps (Upload Resume → AI Analysis → Job Matching → Career Plan) — informational only.

### Your Career Journey (progress tracker)

Tracks your onboarding progress as a percentage bar with four step buttons:

| Step button | What it does |
|---|---|
| **Resume** (Upload & analyze) | Navigates to Resume. Marks ✅ once you have uploaded a resume this session. |
| **Jobs** (Find matches) | Navigates to Jobs. Marks ✅ once a job search has returned results. |
| **Career Plan** (Get roadmap) | Navigates to Career. Marks ✅ once a plan has been generated. |
| **Interview** (Prep & practice) | Navigates to Interview. Marks ✅ once you finish an interview session. |

The **progress %** (`dash-progress-pct`) and fill bar (`dash-progress-fill`) are recomputed
after each milestone: completed steps ÷ 4 (25 % each).

### AI Recommendation banner

| Control | What it does |
|---|---|
| **Get Started** | Navigates to the Resume section. The banner copy changes contextually ("Upload your resume to unlock…"). |

### Quick Actions

| Card | What it does |
|---|---|
| **Upload Resume** | Navigates to Resume. |
| **Find Jobs** | Navigates to Jobs. |
| **ATS Score** | Navigates to Career (ATS scoring is run per job from the Jobs screen — see §5). |
| **AI Coach** | Opens the AI Career Coach chat widget (same as the floating 💬 button). Still requires a configured API key. |

### Testimonials ("What Users Say")

- On load the app calls `GET /api/reviews`. If real reviews exist, three are shuffled in
  and replace the static cards. If none (or on error), the three built-in static
  testimonials stay.

### FAQ

Four accordion items (AI resume analysis, data safety, AI models, own API key).
**Each question button** toggles its answer open/closed (chevron rotates).

### Footer

Product / Resources / Company links and social icons — all are placeholder `#` links.

---

## 3. Resume

Upload and parse your resume (`section-resume`). **The web UI accepts PDF files only**
(the backend parser itself also understands DOCX/TXT).

### Before upload

| Control | What it does |
|---|---|
| **Upload zone** (click anywhere) | Opens the file picker. |
| **Choose File** button | Opens the file picker (same as clicking the zone). |
| **Drag & drop** onto the zone | Uploads the dropped file (zone highlights while dragging). |
| **Tips card** | Static advice (1–2 pages, action verbs, metrics, keywords) — shown only before upload. |

### Upload flow

1. Client-side check: only `application/pdf` is accepted; anything else shows an error toast.
2. `POST /api/resumes` with the file (`FormData`).
3. On success: the upload zone and tips hide; the **resume card** and **next steps** appear;
   a success toast shows; dashboard journey progress updates.

### After upload — resume card

| Element / Control | What it does |
|---|---|
| Filename (PDF icon) | Shows the uploaded file name. |
| **Words** stat | Word count returned by the parser. |
| **Sections** stat | Number of detected sections (experience, education, skills…). |
| Profile area | Shows the parsed professional summary, or a success message if none was detected. |
| **Delete** 🗑 button | Clears the resume from the current session (UI resets to the upload state; toast confirms "Resume removed"). |

### After upload — "What you can do next" cards

| Card | What it does |
|---|---|
| **Find matching jobs** | Navigates to Jobs (use *From My Resume* mode for skill-matched search). |
| **Get your ATS score** | Navigates to Career; run per-job ATS analysis from any job card (§5). |
| **Mock interview** | Navigates to Interview Prep. |

> The resume `resume_id` is held in memory for the session. It is required by
> **From My Resume** job search, **ATS** analysis, **AI Resume Builder**, and
> **Use My Resume** cover letters.

---

## 4. Jobs

Discover roles (`section-jobs`), aggregated from LinkedIn, RemoteOK, and Adzuna.

### Search form

| Control | What it does |
|---|---|
| **Manual Search** tab | Shows the keyword input mode (default). |
| **From My Resume** tab | Switches to resume-based matching; hides the keyword box and shows a hint + readiness status (green "Your resume is ready to use." or red "Upload a resume first…"). |
| **Job Title / Keywords** input | Free text, e.g. "Software Engineer, Python". Required in manual mode. |
| **Location** input | Defaults to "All Countries". |
| **Work Mode** select | Any / Remote / Onsite / Hybrid — sent as the `work_mode` filter. |
| **Search Jobs** button | Manual mode → `POST /api/jobs/search` with `target_role`, `location`, `work_mode`. Resume mode → same endpoint with `resume_id` instead of keywords. Returns up to **15** results. Shows a loading overlay, then a success ("Found N jobs") or "No jobs found" toast. |
| **Quick tags** (Software Engineer, Data Scientist, Product Manager, Designer, Remote) | Fills the keyword box with that term, forces Manual mode, and runs the search immediately. |
| **Empty state card** ("No jobs found yet") | Shown until the first search returns results. |

### Job card (per result)

| Element | What it shows |
|---|---|
| Title + **source badge** | Job title and which board it came from (LinkedIn / RemoteOK / Adzuna). |
| Company | Employer name. |
| **Match score badge** | 0–100 % fit. Green ≥ 60 %, amber 30–59 %, red < 30 %. |
| **Meta pills** | Location, employment type, work mode (Remote/Hybrid/Onsite), salary range (when available). |
| **Match bar** | Visual bar of the same match score. |
| **Missing skills chips** | Up to 4 skills you lack for this role. |
| Description preview | First 200 characters of the listing. |
| **ATS** button | Runs full ATS analysis: `POST /api/jobs/{id}/analyze` with your `resume_id`. On success the card's score updates and the **ATS Analysis modal** opens (§5). Without an uploaded resume it shows a toast instead: "Upload a resume first to run ATS analysis". |
| **AI Resume Builder** button | Tailors your resume to this exact job: `POST /api/resume-optimizer/tailor` with `resume_id`, `job_id`, title, company, and description. Opens the **AI Resume Builder modal** (§6). Requires a resume, otherwise shows a toast. |
| **Apply Now** link | Opens the listing's `source_url` in a new tab. If the source has no URL, falls back to a Google search for `"<title> <company> job apply"`. |

---

## 5. ATS Analysis Modal

Opened by the **ATS** button on a job card. Shows the report returned by the ATS engine.

| Element | What it is |
|---|---|
| Job title / company header | Which role was analyzed. |
| **Score rings + bars** | Six gauges: **Overall Match**, **Keywords**, **Skills**, **Experience**, **Semantic**, **Education** (whichever the report contains), each 0–100 % with green/amber/red color coding. |
| **Missing Keywords** chips | Up to 15 job-description keywords absent from your resume. |
| **Missing Skills** chips | Up to 15 required skills you are missing. |
| **Recommendations** | LLM-written improvement advice, rendered as Markdown. |
| **Close (×)** button | Closes the modal. |

---

## 6. AI Resume Builder Modal

Opened by the **AI Resume Builder** button on a job card. Shows the tailored resume and
lets you export it.

| Element | What it is |
|---|---|
| Target role / company header | The job the resume was tailored for. |
| **What changed** list | Bullet list of edits the optimizer made (summary rewrite, bullet rewrites, keyword additions). |
| **Matched keywords** chips | Up to 24 job keywords now present in your resume, with a count. |
| **Guardrails applied** | Items the optimizer deliberately stripped (e.g. fabricated claims it refused to add). |
| **Resume preview** | Full rendered resume: contact line, Professional Summary, Skills, Professional Experience (title/company/dates/bullets), Projects, Education (incl. GPA), Certifications. |
| **Close (×)** / **Close** button | Closes the modal. |
| **Download DOCX** button | `GET /api/resume-optimizer/{optimized_id}/download` — downloads the tailored resume as a Word document (built server-side with python-docx). |
| **Download PDF** button | Client-side export: renders the tailored resume to a PDF using the vendored jsPDF library — no server call. |

---

## 7. Career Plan

Generates a personalized roadmap (`section-career`).

| Control | What it does |
|---|---|
| **Target Career Field / Role** input | e.g. "Senior Data Engineer", "Machine Learning", "Cloud Architect". Required. |
| **Generate Plan** button | Validates the input client-side (must look like a real profession: ≥2 letters, mostly alphabetic, not a repeated single character — mirrors the backend shape gate), then `POST /api/career/plan`. Shows a loading overlay; on success renders the plan, reveals the **Export PDF** button and the **Roadmap Legend**, and updates dashboard progress. Errors surface as toasts. |
| **Export PDF** button | Appears only after a plan exists. Builds an A4 PDF client-side with jsPDF (skill gaps, roadmap, projects, strategy) and downloads it. |

### What the generated plan contains

| Section | Content |
|---|---|
| **Expertise Roadmap** header | Your target role. |
| **Skill Gaps** | Up to 10 gap cards: priority badge **P1–P5** (P1 red = most urgent) and market demand indicator (high/medium/low with ▲/▼ icon). |
| **Step-by-Step Roadmap** | Ordered steps, each with duration (⏱), "What to learn" topics, "Resources" chips (courses/docs), and a "Practice" assignment. |
| **Portfolio Projects** | Project cards with difficulty (Beginner/Intermediate/Advanced), estimated time, technology chips, and skills practiced. |
| **How to Apply** | Four strategy cards: Resume Tips, Portfolio Tips, Networking, Job Search. |
| **Roadmap Legend** | Explains the three badge colors: Technologies (cogs), Languages (code), Platforms (server). Shown after generation. |

---

## 8. Interview Prep

AI mock interviews (`section-interview`).

### Setup card

| Control | What it does |
|---|---|
| **Job Role** input | The role you are interviewing for (required), e.g. "Senior Software Engineer". |
| **Job Description** textarea | Optional — pasting a JD tailors the generated questions to it. |
| **Interview Type** buttons: **Technical**, **Behavioral**, **Mixed** | Selects the question category mix. **Mixed** is selected by default; only one can be active. |
| **Start Interview** button | `POST /api/interviews` with role, description, and type. On success: hides the setup card, shows the question runner, toasts "N questions ready". |

### Question runner

| Element / Control | What it does |
|---|---|
| **Progress bar** + "Question X of N" | Shows how far through the interview you are. |
| Category + difficulty chips | e.g. `technical` / `medium` for the current question. |
| Question text | The generated question. |
| **Answer textarea** | Type your answer (placeholder encourages specifics and structure). |
| **Submit Answer** button | Requires non-empty text (else error toast). Calls `POST /api/interviews/{id}/answer` with the question index; button becomes "Evaluating…" (disabled) while waiting. |
| **Feedback panel** (appears after submit) | Shows your **score X/10** (green ≥7, amber 4–6, red <4), written feedback, **Strengths** list, **Areas to Improve** list, and a Markdown-rendered **Model Answer**. |
| **Next Question** button | Advances to the next question (visible when not on the last question). |
| **Finish & See Results** button | Appears on the last question. Calls `GET /api/interviews/{id}` and renders the results screen. Also marks the dashboard Interview milestone complete. |

### Results screen

| Element | What it is |
|---|---|
| Overall score X/10 + grade | Grade bands: ≥8 Excellent, ≥6 Good, ≥4 Fair, else Needs Improvement. |
| Score bar | Percentage of questions scored ≥7. |
| Stats row | **Strong** (≥7), **Good** (4–6), **Needs Work** (<4), **Total** question counts. |
| **All Questions Review** | Every question with its category, difficulty, your score, and the correct/model answer. |
| **Retry Weak Questions** button | Re-opens the first question you scored below 7 on, in "Try again" mode with the same submit/feedback flow. If nothing is weak, shows a congratulatory toast. |
| **Download Report** button | Client-side jsPDF export: branded A4 report with overall score, every question, category/difficulty, and correct answers → `interview-report-<role>.pdf`. |
| **New Interview** button | Resets the whole session (clears questions/results, restores the setup card, empties role + JD, recalculates dashboard progress). |

---

## 9. Cover Letter

Generates tailored cover letters (`section-cover-letter`).

| Control | What it does |
|---|---|
| **Fill Details** tab | Manual mode (default): shows Company, Role, and JD fields. |
| **Use My Resume** tab | Hides most fields and shows a hint + readiness status; the letter is generated from your uploaded resume (`resume_id` sent in the payload). Company/Role remain optional in this mode. |
| **Target Company** input | Required in Fill Details mode. |
| **Target Role** input | Required in Fill Details mode. |
| **Job Description** textarea | Optional — improves tailoring. |
| **Tone** buttons: **Professional** (default), **Confident**, **Enthusiastic**, **Creative** | Exactly one active tone is sent as `tone`. |
| **Generate Cover Letter** button | Validates (Fill Details requires company + role; Resume mode requires an uploaded resume — otherwise an error toast), then `POST /api/cover-letters`. Loading overlay → result card + success toast. |
| Result card | Shows the letter text and a meta line "Company — Role — tone". |
| **Copy** button | Copies the letter text to the clipboard; toast confirms "Copied to clipboard". |
| **History** panel | Every letter generated in this session is prepended as a clickable card (company — role, tone, date). **Clicking a history card** reloads that letter into the result card. Session-only (cleared on reload). |

---

## 10. Reviews

Submit and read user reviews (`section-reviews`).

| Control | What it does |
|---|---|
| **Your Name** input | Required. |
| **Your Email** input | Required and must contain `@`. |
| **Your Profession** input | Optional — shown as the role line on the card. |
| **Your Review** textarea | Required. |
| **Submit Review** button | Client-side validation with specific error toasts → `POST /api/reviews`. The button shows a spinner ("Submitting…") and re-enables after completion; fields clear on success. |
| **"What Everyone Says" grid** | All reviews loaded via `GET /api/reviews`, each rendered as a card with generated initials avatar (color hashed from the name), profession, and formatted date. The same feed powers three shuffled testimonials on the Home page. |

---

## 11. Settings

Model and credential configuration (`section-settings`) — the only screen reachable
without an API key.

| Control | What it does |
|---|---|
| **AI Provider** select | Google Gemini / OpenAI / Groq / DeepSeek / Qwen. Changing it repopulates the Model dropdown with that provider's presets (plus Custom). |
| **Model** select | Presets (Gemini 2.5 Flash, Gemini 2.5 Flash Lite, GPT-4o Mini, GPT-4o, Llama 3.3 70B, DeepSeek V3, Qwen Turbo) + **"Custom (type exact model name)"**. |
| **Exact Model Name** input | Appears only when "Custom" is selected. Format `provider/model-name` (e.g. `gemini/gemini-2.5-pro`). Auto-focused when shown. |
| **API Key** input | Password-masked optional override. |
| **Save Model Settings** button | Validates that a model is chosen (error toast otherwise), then saves `aiProvider`, `aiModel`, and (if entered) `aiApiKey` to `localStorage`, toasts "Model settings saved", and re-evaluates the API Key overlay (it disappears once both key and model exist). |

**How it is used:** every API call attaches `X-API-Key` and `X-Model` headers from
`localStorage`, so the backend routes each request to your chosen provider/model. Saved
values are restored on page load; an unrecognized saved model automatically switches the
dropdown to "Custom" and fills the custom input.

---

## 12. AI Career Coach (Chat)

A floating assistant available on every screen.

| Control | What it does |
|---|---|
| **Floating 💬 button** (bottom-right) | Toggles the chat widget open/closed (button animates when active). |
| **Close ×** (widget header) | Closes the widget. |
| **Message textarea** | Enter sends; Shift+Enter inserts a newline; the box auto-grows up to 80 px. |
| **Send** button (paper plane) | Appends your message bubble, shows a three-dot typing indicator, then `POST /api/chat` with `{ message }`. The reply renders as an assistant bubble; the indicator clears. On failure the error renders in red inside the bubble. |
| **chat-meta** area | Holds the typing indicator while waiting. |

The assistant is a LangGraph agent with access to your session data (resume, jobs, ATS
scores, career plans) — see §13.

---

## 13. How the Backend Features Work

Each UI action maps to a LangGraph workflow or deterministic engine:

### Resume parsing (`resume_parser.py`)
PDF (PyMuPDF) or DOCX (python-docx) → raw text → section splitting (summary, experience,
education, skills, projects, certifications) → structured profile with contact extraction
(email/phone/LinkedIn), skill detection against an alias dictionary, date-normalized
experience entries, and education/GPA parsing. Deduplicated by content hash.

### Job discovery & matching (`job_graph.py` + `job_sources/`)
1. **Sources** — LinkedIn Guest API, RemoteOK, Adzuna fetched concurrently via HTTPX
   (manager handles orchestration and fallbacks).
2. **Normalization** — `job_normalizer.py` maps every source into one schema.
3. **Deduplication** — `job_deduplicator.py` merges cross-board duplicates.
4. **Scoring** — multi-factor match: skill overlap (alias-normalized), experience level,
   seniority, location fit, salary fit, and TF-IDF semantic similarity (NumPy). Returns an
   overall 0–1 score (shown as % on the card) plus missing skills.

### ATS analysis (`ats_graph.py` + `ats_engine.py`)
Deterministic scoring across six axes — keyword coverage, skill overlap, experience
alignment, semantic similarity, education, and overall — plus an LLM pass that writes
plain-language recommendations. Returned to the ATS modal and used to refresh the job
card's match score.

### Resume optimizer / AI Resume Builder (`resume_optimizer_graph.py`)
Rewrites your resume for one specific job: targeted summary, keyword-injected bullets,
JD-aligned skills ordering. **Guardrails** strip anything not supported by your original
resume (no fabricated experience) and the report lists what was removed. Output renders in
the modal and exports to DOCX server-side or PDF client-side.

### Career strategist (`career_graph.py`)
Combines skill-gap analysis against market demand (`skill_gap_engine.py`, `market_analyzer.py`)
with LLM generation of a phased roadmap, portfolio projects, and an application strategy.
Also exposes market intel (`GET /api/career/market`) and skill-gap (`GET /api/career/skill-gaps`) endpoints.

### Interview coach (`interview.py` API + LLM)
Generates a question set (technical / behavioral / mixed, optionally grounded in a pasted
JD), evaluates each answer 0–10 with strengths, improvements, and a model answer, then
aggregates an overall score and per-question review.

### Cover letter generator (`cover_letter_graph.py`)
Generates a letter from manual details or your parsed resume, conditioned on the selected
tone (professional / confident / enthusiastic / creative) and optional JD.

### Chat assistant (`chat_graph.py`)
Conversational agent with session context and tool usage (can answer questions about your
resume, matched jobs, ATS scores, and plans). Conversations are stored and listable via
`/api/conversations`.

### Application tracking & ATS stubs (API only)
`/api/applications` (log, list, update status — in-memory) exists but the current UI does
not surface it. The dedicated `/api/ats/*` routes are **stubs** in in-memory mode:
`POST /api/ats/analyze` and `POST /api/ats/optimize` return `501`, `GET /api/ats/reports`
returns an empty list. ATS analysis in the UI runs through `POST /api/jobs/{id}/analyze`,
which invokes the same `ats_graph` pipeline.

### Security (`security/`)
- **Auth** — single guest session per server run; per-request `X-API-Key` / `X-Model` supply LLM credentials.
- **Rate limiting** — 60 requests/minute/IP by default (Redis when `CC_REDIS_URL` is set, in-memory fallback otherwise). Rejections return `429` with `X-RateLimit-*` headers.
- **Sanitization** — user-supplied text is sanitized before it reaches templates/prompts.

### Observability (`observability/`)
Per-request tracing and runtime metrics, surfaced at `GET /api/admin/stats`.

### Model routing (`llm_service.py`)
Requests are served by the model named in your `X-Model` header; otherwise the server
routes to its fast/strong tier (`CC_FAST_MODEL` / `CC_STRONG_MODEL`). Provider factories:
Google Gemini, OpenAI, Groq (DeepSeek/Qwen via OpenAI-compatible endpoints).

---

## 14. Complete API Reference

All endpoints are prefixed with `/api`. Optional headers on every request:

| Header | Purpose |
|---|---|
| `X-API-Key` | LLM credential for this request (set automatically from Settings). |
| `X-Model` | Exact model override, e.g. `openai/gpt-4o-mini`. |

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/health` | Service health and version. |
| GET | `/api/admin/stats` | Runtime statistics (requests, traces). |
| POST | `/api/admin/refresh-jobs` | Force-refresh the job cache. |
| GET | `/api/auth/me` | Current guest user profile. |
| POST | `/api/resumes` | Upload & parse a resume (PDF/DOCX/TXT). |
| GET | `/api/resumes` | List parsed resumes. |
| GET | `/api/resumes/{id}` | Fetch one parsed resume. |
| DELETE | `/api/resumes/{id}` | Delete a parsed resume. |
| POST | `/api/resume-optimizer/tailor` | Tailor a resume to a job description. |
| GET | `/api/resume-optimizer` | List tailored resumes. |
| GET | `/api/resume-optimizer/{id}` | Fetch one tailored resume. |
| GET | `/api/resume-optimizer/{id}/download` | Download tailored resume as DOCX. |
| POST | `/api/jobs/search` | Search jobs (by keywords/target role or `resume_id`), with location & work-mode filters. |
| GET | `/api/jobs` | List cached jobs. |
| GET | `/api/jobs/status/{pipeline_id}` | Async search pipeline status. |
| GET | `/api/jobs/{id}` | Fetch one job. |
| POST | `/api/jobs/{id}/analyze` | Run ATS analysis for a job against a resume. |
| POST | `/api/ats/analyze` | Stub — returns `501` in in-memory mode (use `/api/jobs/{id}/analyze`). |
| GET | `/api/ats/reports` | Stub — returns an empty list in in-memory mode. |
| GET | `/api/ats/reports/{id}` | Stub — returns `404` in in-memory mode. |
| POST | `/api/ats/optimize` | Stub — returns `501` in in-memory mode. |
| POST | `/api/career/plan` | Generate a career plan for a target role. |
| GET | `/api/career/plan` | List generated plans. |
| GET | `/api/career/market` | Market intelligence for a role. |
| GET | `/api/career/skill-gaps` | Skill gap analysis vs market demand. |
| POST | `/api/interviews` | Start an interview session. |
| POST | `/api/interviews/{id}/answer` | Submit an answer for evaluation (returns score, feedback, model answer). |
| GET | `/api/interviews/{id}` | Fetch session results. |
| GET | `/api/interviews/{id}/feedback` | Retrieve interview feedback. |
| POST | `/api/chat` | Send a chat message. |
| GET | `/api/conversations` | List conversations. |
| GET | `/api/conversations/{id}` | Fetch one conversation. |
| DELETE | `/api/conversations/{id}` | Delete a conversation. |
| POST | `/api/cover-letters` | Generate a cover letter. |
| GET | `/api/cover-letters` | List cover letters. |
| GET | `/api/cover-letters/{id}` | Fetch one cover letter. |
| POST | `/api/applications` | Log a job application. |
| GET | `/api/applications` | List applications. |
| PATCH | `/api/applications/{id}` | Update application status. |
| GET | `/api/applications/analytics` | Application statistics (returns empty totals in in-memory mode). |
| POST | `/api/reviews` | Submit a review. |
| GET | `/api/reviews` | List reviews. |
| GET | `/docs` | Interactive Swagger UI (served at the site root). |

---

## 15. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| "API Key Required" overlay won't go away | You saved a model but no key (or vice versa). Both `aiModel` and `aiApiKey` must be set — save them in Settings. |
| "Please upload a PDF file" | The web upload zone accepts PDF only, even though the API also parses DOCX. |
| ATS / AI Resume Builder buttons show a toast instead of working | No resume uploaded in this session — upload one on the Resume page first. |
| "From My Resume" shows red status | Same as above: upload a resume, or use Manual Search. |
| "No jobs found for this role" | Broaden keywords, clear the location (use "All Countries"), or set Work Mode to Any. Sources may also be rate-limited. |
| `429` responses | Hit the 60 req/min/IP rate limit — wait a minute. |
| Plan/interview generation fails | Usually an LLM error: verify the API key is valid for the selected provider, or switch models in Settings. |
| "Please enter a valid profession name" | The career target field must look like a real job title (letters only, ≥2 characters, not one repeated character). |
| Background animation feels heavy | The workflow canvas and blobs are decorative; they can be removed without affecting functionality. |

---

<div align="center">

Built by **Qayoom Ali**

*See [README.md](README.md) for installation, architecture, and setup.*

</div>
