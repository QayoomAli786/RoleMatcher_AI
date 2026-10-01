"""LangGraph StateGraph for job-specific resume tailoring.

Workflow:
    analyze_job -> tailor_resume -> verify_fidelity -> build_resume

The LLM rewrites the resume to mirror a job description. A deterministic
guardrail then strips every claim that is not grounded in the source resume,
so the tailoring rephrases and reorders facts but never invents any.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from langgraph.graph import END, START, StateGraph

from backend.core.schemas import OptimizedExperience, OptimizedResume
from backend.core.state import ResumeOptimizerState
from backend.services.llm_service import ModelRouter, TaskCategory
from backend.services.skill_aliases import normalize_skill

logger = logging.getLogger(__name__)

_router = ModelRouter()


# ── Helpers ─────────────────────────────────────────────────────────────────


_STOP_NOISE = {
    "experience", "experiences", "role", "roles", "job", "jobs", "position",
    "positions", "company", "companies", "team", "teams", "work", "works",
    "working", "year", "years", "ability", "abilities", "skill", "skills",
    "strong", "excellent", "great", "good", "best", "new", "key", "well",
    "environment", "environments", "business", "businesses", "project",
    "projects", "customer", "customers", "client", "clients", "user", "users",
    "quality", "process", "processes", "result", "results", "requirement",
    "requirements", "responsibility", "responsibilities", "candidate",
    "candidates", "hiring", "manager", "team's", "etc", "including", "include",
    "includes", "ensure", "ensuring", "help", "helping", "support", "supporting",
    "provide", "providing", "develop", "developing", "build", "building",
    "learn", "learning", "ability", "opportunity", "opportunities", "plus",
    "benefit", "benefits", "offer", "offers", "package", "salary", "remote",
    "hybrid", "onsite", "office", "full", "part", "time", "based", "looking",
    "seeking", "ideal", "youll", "youre", "weve", "youll",
}

# Words that are normal résumé vocabulary rather than a checkable claim.
_GENERIC_CLAIMS: set[str] = set(_STOP_NOISE) | {
    "communication", "collaboration", "problem", "solving", "analytical",
    "leadership", "management", "development", "design", "designing",
    "engineering", "implementation", "optimization", "optimisation",
    "architecture", "strategic", "innovation", "documentation", "testing",
    "debugging", "deployment", "monitoring", "performance", "scalability",
    "reliability", "security", "agile", "scrum", "methodology", "framework",
    "frameworks", "platform", "platforms", "solution", "solutions",
    "system", "systems", "database", "databases", "web", "cloud", "data",
    "analytics", "technology", "technologies", "tool", "tools", "tooling",
    "functional", "technical", "professional", "experienced", "senior",
    "junior", "mid", "level", "standards", "conventions", "practices",
}

# Section headings that the parser sometimes mistakes for a job title / school
_SECTION_LABELS: set[str] = {
    "experience", "work experience", "professional experience",
    "employment", "employment history", "work history", "career history",
    "education", "academic background", "academic qualifications",
    "qualifications", "skills", "technical skills", "summary",
    "professional summary", "profile", "objective", "projects",
    "certifications", "achievements", "awards", "contact", "personal details",
}

_DATE_ISH = re.compile(r"\b(?:19|20)\d{2}\b|present|current|remote|hybrid", re.IGNORECASE)
_AT_COMPANY = re.compile(
    r"^([A-Z][\w\s&/\-+()]{3,60}?)\s+(?:at|@)\s+([A-Z][\w\s&\-.,()]{2,60})$",
    re.MULTILINE,
)


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9][a-z0-9+#.\-]{1,}", (text or "").lower())


def _candidate_name(profile: dict, resume_text: str = "") -> str:
    """The parsed profile has no name field — pull it from the first résumé line."""
    ci = profile.get("contact_info") or {}
    for source in (ci.get("name"), profile.get("name")):
        if source and str(source).strip():
            return str(source).strip()

    for line in (resume_text or "").splitlines():
        s = line.strip()
        if not s or len(s) > 60:
            continue
        low = s.lower()
        if any(
            k in low
            for k in (
                "resume", "résumé", "curriculum", "vitae", "contact", "email",
                "e-mail", "phone", "summary", "objective", "profile", "experience",
                "education", "skills", "projects", "certifications",
            )
        ):
            continue
        if "@" in s or any(ch.isdigit() for ch in s):
            continue
        words = s.split()
        if 2 <= len(words) <= 4 and all(w[:1].isalpha() for w in words):
            return s
    return ""


def _contact_of(profile: dict, resume_text: str = "") -> dict:
    ci = profile.get("contact_info") or {}
    email = str(ci.get("email", "")).strip()
    website = str(ci.get("website", "")).strip()
    # The parser's website regex happily matches inside the e-mail address
    if website and email and website.lower() in email.lower():
        website = ""
    return {
        "name": _candidate_name(profile, resume_text),
        "email": email,
        "phone": str(ci.get("phone", "")),
        "linkedin": str(ci.get("linkedin", "")),
        "github": str(ci.get("github", "")),
        "website": website,
    }


def _fabricated_terms(text: str, keywords: list[str], terms: set[str]) -> list[str]:
    """Keywords the posting asks for that the candidate never actually mentioned."""
    low = (text or "").lower()
    if not low:
        return []
    found: list[str] = []
    for kw in keywords or []:
        k = (kw or "").strip()
        kl = k.lower()
        # Multi-word phrases are role/context language, not checkable claims
        if len(kl) < 3 or " " in kl or kl in _GENERIC_CLAIMS:
            continue
        if kl in terms:
            continue
        if re.search(r"(?<![a-z0-9])" + re.escape(kl) + r"(?![a-z0-9])", low):
            if k not in found:
                found.append(k)
    return found


def _source_skill_names(profile: dict) -> list[str]:
    names = []
    for s in profile.get("skills", []) or []:
        if isinstance(s, dict):
            n = s.get("name", "")
        else:
            n = str(s)
        if n and n.strip():
            names.append(n.strip())
    return names


def _source_terms(profile: dict, resume_text: str) -> set[str]:
    """Every term the candidate can honestly claim."""
    terms: set[str] = set()
    for n in _source_skill_names(profile):
        terms.add(normalize_skill(n).lower())
    for e in profile.get("experience", []) or []:
        if isinstance(e, dict):
            terms.update(_tokenize(str(e.get("title", "")) + " " + str(e.get("company", ""))))
    terms.update(_tokenize(resume_text))
    return terms


def _fmt_date(value: Any) -> str:
    """date objects serialise as ISO strings — render them human-friendly."""
    if value is None:
        return ""
    s = str(value)
    return s


def _find_role_line(resume_text: str) -> tuple[str, str]:
    """Recover ``Title | Company | ...`` when the parser mistook the heading
    for the job title."""
    for raw in (resume_text or "").splitlines():
        line = raw.strip().lstrip("-*\u2022 \t").strip()
        if not line or len(line) > 130 or "|" not in line:
            continue
        parts = [p.strip() for p in line.split("|") if p.strip()]
        if len(parts) < 2:
            continue
        title, company = parts[0], parts[1]
        if (
            title.lower() in _SECTION_LABELS
            or company.lower() in _SECTION_LABELS
            or _DATE_ISH.search(title)
            or _DATE_ISH.search(company)
            or len(title.split()) > 7
            or len(company.split()) > 6
        ):
            continue
        if not re.match(r"^[A-Za-z][\w\s&#\-+\./\(\)]{2,}$", title):
            continue
        return title, company

    m = _AT_COMPANY.search(resume_text or "")
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return "", ""


def _raw_block_for(lines: list[str], title: str, company: str) -> list[str]:
    """Return the raw-text lines that follow a role heading."""
    tl, cl = title.lower(), company.lower()
    start = -1
    for pass_kind in ("both", "title", "company"):
        for i, ln in enumerate(lines):
            low = ln.lower()
            hit = (
                (pass_kind == "both" and tl and cl and tl in low and cl in low)
                or (pass_kind == "title" and tl and tl in low)
                or (pass_kind == "company" and cl and cl in low)
            )
            if hit:
                start = i
                break
        if start >= 0:
            break
    if start < 0:
        return []

    block: list[str] = []
    for ln in lines[start + 1:]:
        s = ln.strip()
        if not s:
            if block:
                break
            continue
        if s.lower() in _SECTION_LABELS:
            break
        if _DATE_ISH.search(s) and not s[:1] in ("-", "*", "\u2022"):
            break
        block.append(s)
        if len(block) > 12:
            break
    return block


def _source_experience(profile: dict, resume_text: str = "") -> list[dict]:
    """The candidate's real work history.

    Prefers a direct scan of the raw résumé text (which keeps every role and
    every bullet) and only falls back to the generic parser's output, repaired,
    when the scan cannot find any job-header lines.
    """
    entries = [dict(e) for e in (profile.get("experience") or []) if isinstance(e, dict)]

    text_entries = _experience_from_text(resume_text)
    if text_entries:
        by_key = {
            (
                str(e.get("title", "")).strip().lower(),
                str(e.get("company", "")).strip().lower(),
            ): e
            for e in entries
        }
        for t in text_entries:
            src = by_key.get((t["title"].lower(), t["company"].lower()))
            if src:
                for f in ("start_date", "end_date"):
                    if not t.get(f) and src.get(f):
                        t[f] = str(src[f])
                if not t.get("is_current"):
                    t["is_current"] = bool(src.get("is_current"))
                if not t.get("location") and src.get("location"):
                    t["location"] = str(src["location"])
        return [t for t in text_entries if t["title"] or t["company"] or t["bullets"]]

    if not entries:
        return []

    lines = (resume_text or "").splitlines()
    salv_title, salv_company = _find_role_line(resume_text)

    out: list[dict] = []
    for e in entries:
        title = str(e.get("title", "") or "").strip()
        company = str(e.get("company", "") or "").strip()
        heading_taken = title.lower() in _SECTION_LABELS

        if heading_taken:
            title = salv_title or ""
        if not company:
            company = salv_company or ""

        bullets = _split_bullets(str(e.get("description", "") or ""))
        if title and len(bullets) < 2:
            block = _raw_block_for(lines, title, company)
            recovered = [
                s.lstrip("-*\u2022 \t").strip()
                for s in block
                if s[:1] in ("-", "*", "\u2022") and len(s.strip("-*\u2022 \t")) > 3
            ]
            if len(recovered) > len(bullets):
                bullets = recovered
                e["description"] = "\n".join(recovered)

        e["title"] = title
        e["company"] = company
        e["bullets"] = bullets

        if title or company or bullets:
            out.append(e)
    return out


_DEGREE_ISH = re.compile(
    r"\b(?:b\.?s\.?(?:c)?|m\.?s\.?(?:c)?|b\.?a\.?|m\.?a\.?|b\.?tech|m\.?tech|"
    r"mba|bca|mca|ph\.?\s?d|bachelor|master|associate|diploma|certificate)\b",
    re.IGNORECASE,
)
_INSTITUTION_ISH = re.compile(
    r"\b(?:university|college|institute|school|academy|polytechnic|iit|nit|iiit)\b",
    re.IGNORECASE,
)


def _find_education_line(resume_text: str) -> tuple[str, str]:
    """Recover ``Institution | Degree | dates`` when the parser mistook the
    section heading for the school name."""
    for raw in (resume_text or "").splitlines():
        line = raw.strip().lstrip("-*\u2022 \t").strip()
        if not line or len(line) > 130 or "|" not in line:
            continue
        parts = [p.strip() for p in line.split("|") if p.strip()]
        if len(parts) < 2:
            continue
        inst, degree = parts[0], parts[1]
        if inst.lower() in _SECTION_LABELS or degree.lower() in _SECTION_LABELS:
            continue
        if _INSTITUTION_ISH.search(inst) or _DEGREE_ISH.search(degree):
            return inst, degree
    return "", ""


def _source_education(profile: dict, resume_text: str = "") -> list[dict]:
    """Parser education output, repaired with what the raw résumé text says."""
    entries = [dict(e) for e in (profile.get("education") or []) if isinstance(e, dict)]
    if not entries:
        return []

    salv_inst, salv_degree = _find_education_line(resume_text)
    out: list[dict] = []
    for e in entries:
        inst = str(e.get("institution", "") or "").strip()
        degree = str(e.get("degree", "") or "").strip()
        field = str(e.get("field", "") or "").strip()

        if not inst or inst.lower() in _SECTION_LABELS:
            inst = salv_inst or ""
        if not degree and salv_degree and inst == salv_inst:
            degree = salv_degree
        if field.lower() == degree.lower():
            field = ""

        e["institution"], e["degree"], e["field"] = inst, degree, field
        if inst or degree:
            out.append(e)
    return out


def _fallback_resume(
    profile: dict,
    job_title: str,
    company_name: str,
    resume_text: str = "",
) -> OptimizedResume:
    """Deterministic resume build used when the LLM is unavailable."""
    skills = _source_skill_names(profile)
    experience = []
    for exp in _source_experience(profile, resume_text):
        bullets = exp.get("bullets") or []
        if not bullets:
            description = str(exp.get("description", "") or "")
            bullets = [description] if description else []
        experience.append(OptimizedExperience(
            title=str(exp.get("title", "")),
            company=str(exp.get("company", "")),
            location=str(exp.get("location", "")),
            start_date=_fmt_date(exp.get("start_date")),
            end_date=_fmt_date(exp.get("end_date")),
            is_current=bool(exp.get("is_current")),
            bullets=bullets,
        ))

    education = []
    for edu in _source_education(profile, resume_text):
        education.append({
            "institution": str(edu.get("institution", "")),
            "degree": str(edu.get("degree", "")),
            "field": str(edu.get("field", "")),
            "start_date": _fmt_date(edu.get("start_date")),
            "end_date": _fmt_date(edu.get("end_date")),
            "gpa": str(edu.get("gpa", "")) if edu.get("gpa") else "",
        })

    projects = []
    for p in profile.get("projects", []) or []:
        if not isinstance(p, dict):
            continue
        projects.append({
            "name": str(p.get("name", "")),
            "description": str(p.get("description", "")),
            "technologies": [str(t) for t in p.get("technologies", []) or []],
            "bullets": [],
        })

    certifications = []
    for c in profile.get("certifications", []) or []:
        if not isinstance(c, dict):
            continue
        certifications.append({
            "name": str(c.get("name", "")),
            "issuer": str(c.get("issuer", "")),
            "date_obtained": _fmt_date(c.get("date_obtained")),
        })

    return OptimizedResume(
        contact=_contact_of(profile, resume_text),
        target_role=job_title,
        target_company=company_name,
        headline=job_title,
        summary=str(profile.get("summary", "") or ""),
        skills=skills,
        experience=experience,
        education=education,
        projects=projects,
        certifications=certifications,
    )


# ── Nodes ───────────────────────────────────────────────────────────────────


def _casing_score(text: str) -> int:
    """Prefer the properly-spelled variant ('FastAPI' over 'fastapi')."""
    return sum(1 for c in str(text) if c.isupper())


async def analyze_job_node(state: ResumeOptimizerState) -> dict:
    """Deterministically pull the vocabulary of the job posting."""
    from backend.services.ats_engine import _extract_keywords

    job_desc = state.get("job_description", "")
    if not job_desc:
        return {"target_keywords": []}

    candidates: list[str] = list(_extract_keywords(job_desc, top_n=60))

    # Also keep properly-cased / technical-looking terms from the raw text so
    # the prompt and the UI chips show "FastAPI", not "fastapi".
    for tok in re.findall(r"[A-Za-z][A-Za-z0-9+#.\-/]*[A-Za-z0-9+#]", job_desc):
        if tok.lower() in _STOP_NOISE:
            continue
        technical = (
            any(c.isdigit() for c in tok)
            or any(c in "+#./-" for c in tok)
            or tok[:1].isupper()
            or tok != tok.lower()
        )
        if technical:
            candidates.append(tok)

    order: list[str] = []
    picked: dict[str, str] = {}
    for k in candidates:
        lk = k.lower()
        if len(lk) < 3 or any(w in _STOP_NOISE for w in lk.split()):
            continue
        if lk not in picked:
            picked[lk] = k
            order.append(lk)
        elif _casing_score(k) > _casing_score(picked[lk]):
            picked[lk] = k

    return {"target_keywords": [picked[lk] for lk in order][:60]}


async def tailor_resume_node(state: ResumeOptimizerState) -> dict:
    """LLM rewrite of the resume so it mirrors the target job description."""
    profile = state.get("resume_profile", {}) or {}
    resume_text = state.get("resume_text", "") or ""
    job_desc = state.get("job_description", "") or ""
    job_title = state.get("job_title", "") or "the target role"
    company = state.get("company_name", "") or "the company"
    keywords = state.get("target_keywords", []) or []

    source_skills = _source_skill_names(profile)
    contact = _contact_of(profile, resume_text)

    experience_blocks = []
    for exp in profile.get("experience", []) or []:
        if isinstance(exp, dict):
            experience_blocks.append(
                f"- {exp.get('title', '')} | {exp.get('company', '')} | "
                f"{_fmt_date(exp.get('start_date'))} to {_fmt_date(exp.get('end_date'))} | "
                f"{exp.get('description', '')}"
            )

    prompt = f"""You are an expert resume writer and ATS optimisation specialist.

Rewrite the candidate's resume so it is tailored to the job below.
The result must be a SINGLE JSON object and nothing else.

TARGET ROLE: {job_title}
TARGET COMPANY: {company}

JOB DESCRIPTION:
{job_desc[:4000]}

JOB KEYWORDS: {', '.join(keywords[:40])}

CANDIDATE CONTACT (use verbatim):
{contact.get('name', '')} | {contact.get('email', '')} | {contact.get('phone', '')} | {contact.get('linkedin', '')} | {contact.get('github', '')} | {contact.get('website', '')}

CANDIDATE SUMMARY:
{(profile.get('summary') or '')[:800]}

CANDIDATE SKILLS (the ONLY skills you may list):
{', '.join(source_skills)}

CANDIDATE EXPERIENCE:
{chr(10).join(experience_blocks) or '(none)'}

ORIGINAL RESUME (raw extracted text — the source of truth for every bullet):
{resume_text[:6000]}

--- ABSOLUTE RULES ---
1. NEVER INVENT. You may NOT add any skill, technology, employer, job title, date,
   degree, certification, project, link, metric or percentage that is NOT already in
   the source resume above. Reordering, regrouping and rephrasing existing facts is
   required and encouraged; fabrication is forbidden.
2. Use the job posting's exact vocabulary where it describes something the candidate
   genuinely already has (e.g. if the posting says "CI/CD" and the resume says
   "continuous integration", use "CI/CD").
3. Mirror the job title in the headline/target_role only if the candidate's actual
   titles support it; otherwise keep their real titles.
4. Every bullet must be ONE line, achievement-oriented, starting with a strong verb
   (Built, Led, Delivered, Optimised, Designed...). Keep bullets under 24 words.
5. Do not fabricate numbers. If the source has no metric, write no metric.
6. summary: 3-4 sentences, keyword-rich, written for this specific role.
7. skills: keep only real candidate skills, ordered so the ones this job cares about
   most come first.

--- JSON SHAPE ---
{{
  "contact": {{"name":"","email":"","phone":"","linkedin":"","github":"","website":""}},
  "target_role": "",
  "target_company": "",
  "headline": "",
  "summary": "",
  "skills": ["..."],
  "experience": [
    {{"title":"","company":"","location":"","start_date":"","end_date":"",
      "is_current": false, "bullets": [""]}}
  ],
  "education": [
    {{"institution":"","degree":"","field":"","start_date":"","end_date":"","gpa":""}}
  ],
  "projects": [
    {{"name":"","description":"","technologies":[""],"bullets":[""]}}
  ],
  "certifications": [
    {{"name":"","issuer":"","date_obtained":""}}
  ]
}}

Return only the JSON object."""

    try:
        result = await _router.structured(
            messages=[{"role": "user", "content": prompt}],
            schema=OptimizedResume,
            category=TaskCategory.RESUME_REWRITE,
        )
        if isinstance(result, OptimizedResume):
            return {"optimized": result.model_dump()}
        return {"optimized": OptimizedResume.model_validate(result).model_dump()}
    except Exception as exc:
        logger.warning("Resume tailoring LLM failed, using fallback: %s", exc)
        fallback = _fallback_resume(profile, job_title, company, resume_text)
        return {
            "optimized": fallback.model_dump(),
            "error": None,
        }


async def _repair_summary(text: str, offenders: list[str], job_title: str) -> str:
    """Ask the model to strip the specific unverified claims it introduced."""
    prompt = (
        "This professional summary belongs to a candidate's resume. It mentions "
        "things that are NOT in the candidate's real background:\n"
        + "\n".join(f"- {o}" for o in offenders)
        + "\n\nRewrite the summary so it no longer mentions any of them. Keep the "
        "same tone, roughly the same length, and every other detail intact. "
        f"It is being tailored for a {job_title} role.\n\n"
        f"SUMMARY:\n{text}\n\n"
        "Return only the rewritten summary — no commentary."
    )
    try:
        result = await _router.complete(
            messages=[{"role": "user", "content": prompt}],
            category=TaskCategory.RESUME_REWRITE,
        )
        return str(result).strip()
    except Exception as exc:
        logger.warning("Summary repair failed: %s", exc)
        return ""


async def verify_fidelity_node(state: ResumeOptimizerState) -> dict:
    """Deterministic guardrail — strip anything not grounded in the source resume."""
    optimized = state.get("optimized") or {}
    profile = state.get("resume_profile", {}) or {}
    resume_text = state.get("resume_text", "") or ""
    keywords = list(state.get("target_keywords") or [])

    if not optimized:
        return {}

    original = _fallback_resume(
        profile,
        state.get("job_title", ""),
        state.get("company_name", ""),
        resume_text,
    )
    stripped: list[str] = []

    # 1. Contact must match the uploaded resume exactly
    source_contact = _contact_of(profile, resume_text)
    if not optimized.get("contact"):
        optimized["contact"] = source_contact
    else:
        for field in ("email", "phone", "linkedin", "github", "website", "name"):
            src = source_contact.get(field, "")
            cur = (optimized.get("contact") or {}).get(field, "")
            if src and cur and src.lower() != cur.lower():
                stripped.append(f"{field} corrected to match your resume")
                optimized["contact"][field] = src
            elif src and not cur:
                optimized["contact"][field] = src

    # 2. Skills must all be genuinely present in the source
    source_skills = _source_skill_names(profile)
    source_norm = {normalize_skill(s).lower(): s for s in source_skills}
    terms = _source_terms(profile, resume_text)
    kept_skills: list[str] = []
    for skill in optimized.get("skills", []) or []:
        key = normalize_skill(str(skill)).lower()
        if key in source_norm:
            if source_norm[key] not in kept_skills:
                kept_skills.append(source_norm[key])
        elif key and key in terms:
            if str(skill) not in kept_skills:
                kept_skills.append(str(skill))
        else:
            stripped.append(f'Removed unverified skill "{skill}"')
    if not kept_skills:
        kept_skills = source_skills
    optimized["skills"] = kept_skills

    # 2b. The summary may not claim tools, employers or credentials
    #     the candidate never mentioned.
    summary = str(optimized.get("summary") or "").strip()
    source_summary = str(profile.get("summary", "") or "").strip()
    if summary:
        offenders = _fabricated_terms(summary, keywords, terms)
        if offenders and terms:
            repaired = await _repair_summary(
                summary, offenders, state.get("job_title", "")
            )
            if repaired and not _fabricated_terms(repaired, keywords, terms):
                optimized["summary"] = repaired
                stripped.append(
                    "Removed unverified claims from the summary: "
                    + ", ".join(offenders[:4])
                )
            elif source_summary:
                optimized["summary"] = source_summary
                stripped.append(
                    "Summary restored from your resume — the rewrite "
                    "contained unverified claims"
                )
            else:
                optimized["summary"] = ""
                stripped.append("Summary removed — it contained unverified claims")

    # 3. Experience entries must resolve back to a real role in the source résumé
    source_exps = _source_experience(profile, resume_text)
    known_companies = {
        str(s.get("company", "") or "").strip().lower()
        for s in source_exps
        if str(s.get("company", "") or "").strip()
    }
    known_titles = {
        str(s.get("title", "") or "").strip().lower()
        for s in source_exps
        if str(s.get("title", "") or "").strip()
    }
    low_text = (resume_text or "").lower()

    def _grounded(t: str, c: str) -> bool:
        """Is this role something the candidate's own résumé actually says?"""
        tl_, cl_ = t.lower().strip(), c.lower().strip()
        if tl_ in _SECTION_LABELS and not cl_:
            return False
        if cl_ and any(cl_ == k or cl_ in k or k in cl_ for k in known_companies):
            return True
        if tl_ and tl_ in known_titles:
            return True
        # The raw résumé text is the ultimate source of truth
        if tl_ and tl_ in low_text and (not cl_ or cl_ in low_text):
            return True
        if cl_ and cl_ in low_text and (not tl_ or tl_ in low_text):
            return True
        return False

    def _company_hit(src: dict, company_low: str) -> bool:
        s = str(src.get("company", "") or "").strip().lower()
        return bool(company_low) and bool(s) and (company_low == s or company_low in s or s in company_low)

    def _title_hit(src: dict, title_low: str) -> bool:
        if not title_low or title_low in _SECTION_LABELS:
            return False
        return str(src.get("title", "") or "").strip().lower() == title_low

    def _grounded_bullet(text: str) -> bool:
        """A bullet must be traceable to the candidate's own resume."""
        low = str(text or "").strip().lower()
        if not low:
            return True
        if low in low_text:
            return True
        # Quantified claims: the number itself has to appear in the source
        for num in re.findall(r"\d[\d,.]*\d|\d", low):
            if num not in low_text:
                return False
        content = [t for t in _tokenize(low) if t not in _GENERIC_CLAIMS and len(t) > 2]
        if not content:
            return True
        return any(t in low_text for t in content)

    verified_experience = []
    used_source: set[int] = set()
    for exp in optimized.get("experience", []) or []:
        company = str(exp.get("company", "") or "").strip()
        title = str(exp.get("title", "") or "").strip()
        cl = company.lower()
        tl = title.lower()

        hits = [
            i for i, src in enumerate(source_exps)
            if _company_hit(src, cl) or _title_hit(src, tl)
        ]
        free = [i for i in hits if i not in used_source]
        source_index = free[0] if free else None
        source_entry = source_exps[source_index] if source_index is not None else None

        if source_index is None:
            if hits:
                stripped.append("Removed a duplicate experience entry that is not in your resume")
                continue
            if not _grounded(title, company):
                label = company or title
                if label and tl not in _SECTION_LABELS:
                    stripped.append(f"Removed unverified experience \u201c{label}\u201d")
                continue
        else:
            used_source.add(source_index)

        # Employer, title, location and dates are ground truth — never the model's
        src_company = str((source_entry or {}).get("company", "") or "").strip()
        src_title = str((source_entry or {}).get("title", "") or "").strip()
        if src_company:
            if company and src_company.lower() != cl and tl not in _SECTION_LABELS:
                stripped.append(
                    f'Replaced unverified employer \u201c{company}\u201d '
                    f'with \u201c{src_company}\u201d'
                )
            exp["company"] = src_company
        if src_title and src_title.lower() not in _SECTION_LABELS:
            exp["title"] = src_title
        elif tl in _SECTION_LABELS:
            exp["title"] = ""
        src_location = str((source_entry or {}).get("location", "") or "").strip()
        if src_location:
            exp["location"] = src_location

        dates_changed = False
        for f in ("start_date", "end_date"):
            new = str((source_entry or {}).get(f) or "")
            old = str(exp.get(f) or "")
            if new and old and new != old:
                dates_changed = True
            if new:
                exp[f] = new
        if dates_changed:
            stripped.append("Restored your original employment dates")
        if source_entry:
            exp["is_current"] = bool(source_entry.get("is_current"))

        # Bullets may not name a job keyword the candidate never mentioned
        clean_bullets = []
        removed_count = 0
        for bullet in exp.get("bullets", []) or []:
            text = str(bullet).strip()
            if not text:
                continue
            b_tokens = set(_tokenize(text))
            fabricated = [
                kw for kw in keywords
                if kw.lower() in b_tokens
                and kw.lower() not in terms
                and kw.lower() not in _GENERIC_CLAIMS
            ]
            if fabricated:
                removed_count += 1
                stripped.append(
                    f'Removed a bullet claiming {", ".join(fabricated[:3])} '
                    "which is not in your resume"
                )
                continue
            if not _grounded_bullet(text):
                removed_count += 1
                stripped.append("Removed a bullet that is not supported by your resume")
                continue
            clean_bullets.append(text)
        exp["bullets"] = clean_bullets

        # Top the entry back up with real bullets whenever one was removed
        real = _split_bullets(str((source_entry or {}).get("description", "") or ""))
        if not real and (source_entry or {}).get("description"):
            real = [str(source_entry["description"]).strip()]

        if removed_count and real:
            kept_low = {b.lower() for b in exp["bullets"]}
            need = removed_count
            for rb in real:
                if need <= 0:
                    break
                if rb.lower() not in kept_low:
                    exp["bullets"].append(rb)
                    kept_low.add(rb.lower())
                    need -= 1

        if not exp["bullets"]:
            exp["bullets"] = real

        verified_experience.append(exp)

    if verified_experience:
        optimized["experience"] = verified_experience
    elif profile.get("experience"):
        optimized["experience"] = [e.model_dump() for e in original.experience]
        stripped.append("Experience section restored from your resume")
    else:
        optimized["experience"] = []

    # 4. Education institutions must be real
    source_edu = _source_education(profile, resume_text)
    source_inst = {
        str(e.get("institution", "")).strip().lower()
        for e in source_edu
        if str(e.get("institution", "") or "").strip()
    }
    had_edu = bool(optimized.get("education"))
    kept_edu = []
    for edu in optimized.get("education", []) or []:
        if str(edu.get("field", "") or "").strip().lower() == str(
            edu.get("degree", "") or ""
        ).strip().lower():
            edu["field"] = ""
        inst = str(edu.get("institution", "") or "").strip()
        low = inst.lower()
        if low in _SECTION_LABELS:
            continue
        if not inst or low in source_inst or any(low in s or s in low for s in source_inst if s):
            kept_edu.append(edu)
        else:
            stripped.append(f'Removed unverified education "{inst}"')

    if kept_edu:
        optimized["education"] = kept_edu
    else:
        optimized["education"] = source_edu
        if had_edu and source_edu:
            stripped.append("Education section restored from your resume")

    # 5. Projects and certifications must already exist in the source
    source_project_names = {
        str(p.get("name", "")).strip().lower()
        for p in profile.get("projects", []) or []
        if isinstance(p, dict) and p.get("name")
    }
    optimized["projects"] = [
        p for p in (optimized.get("projects") or [])
        if str(p.get("name", "")).strip().lower() in source_project_names
    ]

    source_cert_names = {
        str(c.get("name", "")).strip().lower()
        for c in profile.get("certifications", []) or []
        if isinstance(c, dict) and c.get("name")
    }
    optimized["certifications"] = [
        c for c in (optimized.get("certifications") or [])
        if str(c.get("name", "")).strip().lower() in source_cert_names
    ]

    # 6. Target role / company are the job's, never invented by the model
    optimized["target_role"] = state.get("job_title") or optimized.get("target_role", "")
    optimized["target_company"] = state.get("company_name") or optimized.get("target_company", "")
    # Headline is rebuilt deterministically in build_resume_node
    optimized["headline"] = optimized.get("target_role", "")

    return {"optimized": optimized, "stripped": stripped}


async def build_resume_node(state: ResumeOptimizerState) -> dict:
    """Compute matched keywords, a deterministic headline and a change log."""
    profile = state.get("resume_profile", {}) or {}
    resume_text = state.get("resume_text", "") or ""

    optimized = dict(state.get("optimized") or {})
    if not optimized:
        optimized = _fallback_resume(
            profile,
            state.get("job_title", ""),
            state.get("company_name", ""),
            resume_text,
        ).model_dump()

    terms = _source_terms(profile, resume_text)
    keywords = state.get("target_keywords", []) or []
    source_skills = _source_skill_names(profile)

    # The parser lowercases skills — reuse the posting's spelling where it is better
    casing_map = {
        normalize_skill(kw).lower(): kw
        for kw in keywords
        if _casing_score(kw) > _casing_score(normalize_skill(kw))
    }

    matched: list[str] = []
    for kw in keywords:
        low = str(kw).lower()
        if low in _STOP_NOISE or len(low) < 3:
            continue
        if low in terms or normalize_skill(kw).lower() in terms or low in resume_text.lower():
            canonical = next(
                (s for s in source_skills if normalize_skill(s).lower() == normalize_skill(kw).lower()),
                kw,
            )
            if _casing_score(kw) > _casing_score(canonical):
                canonical = kw
            if canonical not in matched:
                matched.append(canonical)
    optimized["matched_keywords"] = matched[:30]

    optimized["skills"] = [
        casing_map.get(normalize_skill(s).lower(), s)
        for s in optimized.get("skills", [])
    ]

    # Deterministic, fully grounded headline: role plus top matched skills
    role = optimized.get("target_role") or state.get("job_title") or ""
    matched_low = {m.lower() for m in matched}
    top = [
        s for s in optimized.get("skills", [])
        if s.lower() in matched_low or normalize_skill(s).lower() in {
            normalize_skill(m).lower() for m in matched
        }
    ][:3]
    if role and top:
        optimized["headline"] = f"{role} \u2014 {', '.join(top)}"
    else:
        optimized["headline"] = role

    changes: list[str] = []
    src_summary = str(profile.get("summary", "") or "").strip()
    if optimized.get("summary") and optimized["summary"].strip() != src_summary:
        changes.append("Professional summary rewritten for this role")

    src_skills = [
        casing_map.get(normalize_skill(s).lower(), s) for s in source_skills
    ]
    if optimized.get("skills") and optimized["skills"] != src_skills:
        leading = optimized["skills"][:5]
        changes.append(f"Skills reordered to lead with {', '.join(leading)}")

    src_bullets = sum(
        len(e.get("bullets") or _split_bullets(str(e.get("description", ""))))
        for e in _source_experience(profile, resume_text)
    )
    new_bullets = sum(len(e.get("bullets", [])) for e in optimized.get("experience", []))
    if new_bullets and new_bullets != src_bullets:
        changes.append(
            f"Experience bullets condensed to {new_bullets} "
            "achievement-focused lines"
        )

    if matched:
        changes.append(f"Aligned wording with {len(matched)} keywords from the posting")

    role = state.get("job_title") or ""
    company = state.get("company_name") or ""
    if role:
        who = f"the {role} role" if not company else f"the {role} role at {company}"
        changes.append(f"Headline and framing targeted at {who}")

    optimized["changes"] = changes
    return {"optimized": optimized}


def _split_bullets(text: str) -> list[str]:
    out = []
    for b in re.split(r"[\n\r]+|\s*;\s*|\s\*\s+", text or ""):
        b = b.strip().lstrip("-*\u2022 \u25aa \t").strip()
        if b:
            out.append(b)
    return out


_MON = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?"
_DATE = rf"(?:{_MON}\s+)?(?:19|20)\d{{2}}(?:-\d{{1,2}}(?:-\d{{1,2}})?)?"
_DATE_RANGE = re.compile(
    rf"({_DATE})\s*(?:-|\u2013|\u2014|to)\s*({_DATE}|present|current|now)",
    re.IGNORECASE,
)


def _parse_role_header(raw_line: str) -> tuple[str, str] | None:
    """Recognise ``Title | Company | Location | dates`` / ``Title at Company``.

    Returns ``(title, company)`` or ``None`` when the line is not a job header.
    """
    raw = (raw_line or "").strip()
    s = raw.lstrip("-*\u2022\u25aa \t").strip()
    had_marker = s != raw
    if not s or len(s) > 140:
        return None
    if s.lower().rstrip(":") in _SECTION_LABELS:
        return None

    if "|" in s:
        parts = [p.strip() for p in s.split("|") if p.strip()]
        if len(parts) < 2:
            return None
        title, company = parts[0], parts[1]
        # Education lines share this shape — never treat them as jobs
        if _INSTITUTION_ISH.search(title) or _DEGREE_ISH.search(title):
            return None
        if _INSTITUTION_ISH.search(company) or _DEGREE_ISH.search(company):
            return None
        if _DEGREE_ISH.search(s):
            return None
    else:
        # Bullets such as "Led the API team at Google" must not become jobs
        if had_marker:
            return None
        m = _AT_COMPANY.match(s)
        if not m:
            return None
        if not re.search(r"(?:19|20)\d{2}|present|current", s, re.IGNORECASE):
            return None
        title, company = m.group(1).strip(), m.group(2).strip()

    if not title or not company:
        return None
    if title.lower() in _SECTION_LABELS or company.lower() in _SECTION_LABELS:
        return None
    if len(title) > 60 or len(company) > 60:
        return None
    # Contact details ("jane@x.com | 555-0101 | …") are not job headers
    if "@" in title or "@" in company:
        return None
    if re.fullmatch(r"[\d\s().+\-/]+", company):
        return None
    if not re.search(r"[A-Za-z]{3,}", title) or not re.search(r"[A-Za-z]{3,}", company):
        return None
    return title, company


def _experience_from_text(resume_text: str) -> list[dict]:
    """Rebuild the work history straight from the raw résumé text.

    The generic parser collapses several roles into one entry and drops the
    opening bullet; scanning for job-header lines avoids both problems.
    """
    lines = [l for l in (resume_text or "").splitlines() if l.strip()]
    headers = [(i, _parse_role_header(l)) for i, l in enumerate(lines)]
    starts = [i for i, h in headers if h]
    if not starts:
        return []

    out: list[dict] = []
    for n, i in enumerate(starts):
        title, company = headers[i][1] or ("", "")
        end = starts[n + 1] if n + 1 < len(starts) else len(lines)

        header_line = lines[i].lstrip("-*\u2022\u25aa \t").strip()
        location = ""
        if "|" in header_line:
            parts = [p.strip() for p in header_line.split("|") if p.strip()]
            if len(parts) >= 3:
                cand = parts[2]
                if not re.search(r"(?:19|20)\d{2}", cand) and cand.lower() not in (
                    "present", "current", "now",
                ):
                    location = cand

        is_current, start_date, end_date = False, "", ""
        m = _DATE_RANGE.search(header_line)
        if m:
            start_date = m.group(1).strip()
            tail = m.group(2).strip().lower()
            is_current = tail in ("present", "current", "now")
            if not is_current:
                end_date = m.group(2).strip()

        bullets: list[str] = []
        for raw in lines[i + 1:end]:
            s = raw.strip().lstrip("-*\u2022\u25aa \t").strip()
            if not s:
                continue
            if s.lower().rstrip(":") in _SECTION_LABELS:
                break  # reached SKILLS / EDUCATION / …
            bullets.append(s)

        if title or company:
            out.append({
                "title": title,
                "company": company,
                "location": location,
                "start_date": start_date,
                "end_date": end_date,
                "is_current": is_current,
                "description": "\n".join(bullets),
                "bullets": bullets,
            })
    return out


async def error_node(state: ResumeOptimizerState) -> dict:
    logger.error("Resume optimisation failed for user=%s", state.get("user_id"))
    return {"error": "Resume optimisation failed. Please try again."}


# ── Graph ───────────────────────────────────────────────────────────────────


def build_resume_optimizer_graph() -> StateGraph:
    graph = StateGraph(ResumeOptimizerState)

    graph.add_node("analyze_job", analyze_job_node)
    graph.add_node("tailor_resume", tailor_resume_node)
    graph.add_node("verify_fidelity", verify_fidelity_node)
    graph.add_node("build_resume", build_resume_node)
    graph.add_node("error_node", error_node)

    graph.add_edge(START, "analyze_job")
    graph.add_edge("analyze_job", "tailor_resume")
    graph.add_edge("tailor_resume", "verify_fidelity")
    graph.add_edge("verify_fidelity", "build_resume")
    graph.add_edge("build_resume", END)
    graph.add_edge("error_node", END)

    return graph


resume_optimizer_pipeline = build_resume_optimizer_graph().compile()
