"""Deterministic ATS scoring: keyword coverage, skill coverage, experience, education, format."""

from __future__ import annotations

import math
import re
from collections import Counter

from backend.core.schemas import ATSReport, ResumeProfile

# ── Stopwords ─────────────────────────────────────────────────────────────────

_STOPWORDS: set[str] = {
    "a", "an", "the", "and", "or", "but", "is", "are", "was", "were", "be",
    "been", "being", "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "shall", "can", "need", "dare", "ought",
    "used", "to", "of", "in", "for", "on", "with", "at", "by", "from", "as",
    "into", "through", "during", "before", "after", "above", "below", "between",
    "out", "off", "over", "under", "again", "further", "then", "once", "here",
    "there", "when", "where", "why", "how", "all", "both", "each", "few",
    "more", "most", "other", "some", "such", "no", "nor", "not", "only", "own",
    "same", "so", "than", "too", "very", "just", "because", "if", "that",
    "this", "these", "those", "it", "its", "they", "them", "their", "what",
    "which", "who", "whom", "while", "we", "you", "your", "our", "my", "me",
    "he", "she", "him", "her", "about", "up", "also", "well", "back", "even",
    "still", "new", "like", "good", "make", "know", "take", "come", "see",
    "think", "want", "give", "use", "find", "tell", "ask", "work", "seem",
    "feel", "try", "leave", "call", "set", "move", "show", "help", "turn",
    "start", "run", "hold", "keep", "let", "begin", "get", "put", "end",
    "add", "go", "say", "said", "way", "many", "much", "any", "us",
}

_WORD_RE = re.compile(r"[a-z0-9]+(?:[-_][a-z0-9]+)*", re.IGNORECASE)


def _tokenize(text: str) -> list[str]:
    return [w.lower() for w in _WORD_RE.findall(text) if w.lower() not in _STOPWORDS and len(w) > 1]


def _extract_keywords(text: str, top_n: int = 40) -> list[str]:
    """TF-based keyword extraction (deterministic, no sklearn needed)."""
    tokens = _tokenize(text)
    counts = Counter(tokens)
    bigrams = [f"{tokens[i]} {tokens[i+1]}" for i in range(len(tokens) - 1)]
    bg_counts = Counter(bigrams)

    for bg, cnt in bg_counts.items():
        counts[bg] = cnt * 2

    return [word for word, _ in counts.most_common(top_n)]


# ── Score Components ──────────────────────────────────────────────────────────


def _keyword_score(resume_text: str, job_keywords: list[str]) -> tuple[float, list[str]]:
    resume_lower = resume_text.lower()
    present = [kw for kw in job_keywords if kw in resume_lower]
    missing = [kw for kw in job_keywords if kw not in resume_lower]

    if not job_keywords:
        return 100.0, []

    score = (len(present) / len(job_keywords)) * 100
    return round(score, 1), missing


def _skill_score(resume_skills: list[str], job_keywords: list[str]) -> tuple[float, list[str]]:
    resume_set = {s.lower() for s in resume_skills}
    job_set = {k.lower() for k in job_keywords}

    # Include aliases
    _ALIASES: dict[str, set[str]] = {
        "javascript": {"js"}, "typescript": {"ts"}, "python": {"py"},
        "react": {"reactjs", "react.js"}, "vue": {"vuejs", "vue.js"},
        "angular": {"angularjs", "angular.js"}, "node": {"nodejs", "node.js"},
        "kubernetes": {"k8s"}, "postgresql": {"postgres"},
        "mongodb": {"mongo"}, "dynamodb": {"dynamo"},
        "tensorflow": {"tf"}, "pytorch": {"pt"},
        "scikit-learn": {"sklearn"},
    }

    for canonical, aliases in _ALIASES.items():
        if canonical in resume_set:
            resume_set.update(aliases)
        for a in aliases:
            if a in resume_set:
                resume_set.add(canonical)

    matched = resume_set & job_set
    missing = list(job_set - resume_set)

    if not job_set:
        return 100.0, []

    score = (len(matched) / len(job_set)) * 100
    return round(score, 1), missing


def _experience_score(resume_profile: ResumeProfile, required_years: float = 3.0) -> float:
    years = resume_profile.years_experience
    if years >= required_years:
        return 100.0
    ratio = years / required_years if required_years > 0 else 1.0
    return round(min(ratio * 100, 95.0), 1)


def _education_score(resume_profile: ResumeProfile, required_keywords: list[str] | None = None) -> float:
    if not resume_profile.education:
        return 30.0

    has_bachelor = any(
        any(kw in edu.degree.lower() for kw in ["bachelor", "b.s.", "b.a.", "b.tech", "bs", "ba"])
        for edu in resume_profile.education
    )
    has_master = any(
        any(kw in edu.degree.lower() for kw in ["master", "m.s.", "m.a.", "m.tech", "ms", "ma", "mba", "msc"])
        for edu in resume_profile.education
    )
    has_phd = any(
        any(kw in edu.degree.lower() for kw in ["phd", "ph.d", "doctorate", "doctoral"])
        for edu in resume_profile.education
    )

    if has_phd:
        return 100.0
    if has_master:
        return 85.0
    if has_bachelor:
        return 70.0
    return 40.0


def _format_score(resume_profile: ResumeProfile, resume_text: str) -> float:
    score = 0.0
    max_score = 7.0

    if resume_profile.contact_info.email:
        score += 1
    if resume_profile.contact_info.phone or resume_profile.contact_info.linkedin:
        score += 1
    if resume_profile.summary:
        score += 1
    if resume_profile.skills:
        score += 1
    if resume_profile.experience:
        score += 1
    if resume_profile.education:
        score += 1
    text_len = len(resume_text)
    if 200 <= text_len <= 5000:
        score += 1

    return round((score / max_score) * 100, 1)


def _extract_required_years(job_description: str) -> float:
    patterns = [
        re.compile(r"(\d+)\+?\s*years?\s*(?:of\s+)?(?:experience|exp)", re.I),
        re.compile(r"(\d+)\s*to\s*(\d+)\s*years?\s*(?:of\s+)?(?:experience|exp)", re.I),
    ]
    for pat in patterns:
        m = pat.search(job_description)
        if m:
            if m.lastindex and m.lastindex >= 2:
                return (float(m.group(1)) + float(m.group(2))) / 2
            return float(m.group(1))
    return 3.0


# ── Recommendations ───────────────────────────────────────────────────────────


def _generate_recommendations(
    kw_missing: list[str],
    skill_missing: list[str],
    scores: dict[str, float],
) -> list[str]:
    recs: list[str] = []

    if kw_missing:
        recs.append(
            f"Add these keywords to your resume: {', '.join(kw_missing[:8])}"
        )

    if skill_missing:
        recs.append(
            f"Highlight these skills if you have them: {', '.join(skill_missing[:6])}"
        )

    if scores.get("keyword", 100) < 50:
        recs.append("Rewrite your summary to mirror language from the job description.")

    if scores.get("format", 100) < 60:
        recs.append("Ensure your resume has: contact info, summary, skills, experience, and education sections.")

    if scores.get("experience", 100) < 50:
        recs.append("Quantify your experience with metrics (e.g., 'Led team of 5', 'Reduced latency by 40%').")

    if not recs:
        recs.append("Your resume is well-optimized for this job.")

    return recs


# ── Main API ──────────────────────────────────────────────────────────────────


def calculate_ats_score(
    resume_text: str,
    job_description: str,
    resume_profile: ResumeProfile,
) -> ATSReport:
    """
    Calculate a deterministic ATS score for a resume against a job description.
    No LLM involved — pure regex + TF keyword extraction + schema scoring.
    """
    job_keywords = _extract_keywords(job_description, top_n=40)
    skill_names = [s.name for s in resume_profile.skills]

    kw_score, kw_missing = _keyword_score(resume_text, job_keywords)
    sk_score, sk_missing = _skill_score(skill_names, job_keywords)

    required_years = _extract_required_years(job_description)
    exp_score = _experience_score(resume_profile, required_years)
    edu_score = _education_score(resume_profile)
    fmt_score = _format_score(resume_profile, resume_text)

    scores = {
        "keyword": kw_score,
        "skill": sk_score,
        "experience": exp_score,
        "education": edu_score,
        "format": fmt_score,
    }

    overall = (
        kw_score * 0.25
        + sk_score * 0.25
        + exp_score * 0.20
        + edu_score * 0.15
        + fmt_score * 0.15
    )

    recommendations = _generate_recommendations(kw_missing, sk_missing, scores)

    return ATSReport(
        overall_score=round(overall, 1),
        keyword_score=kw_score,
        skill_score=sk_score,
        experience_score=exp_score,
        semantic_score=kw_score,
        education_score=edu_score,
        missing_keywords=kw_missing,
        missing_skills=sk_missing,
        recommendations=recommendations,
        improved_sections={},
    )
