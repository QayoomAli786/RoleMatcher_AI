"""LangGraph StateGraph for career planning — optimized single-call pipeline.

Workflow:
    analyze_current_state -> analyze_market -> identify_gaps -> generate_full_roadmap -> synthesize_plan

All LLM reasoning happens in a single ``generate_full_roadmap`` call, cutting
latency from ~60 s (5 sequential calls) to ~8-12 s.
"""

from __future__ import annotations

import json
import logging
from typing import Literal

from langgraph.graph import END, START, StateGraph

from backend.core.schemas import CareerPlan, SkillGap
from backend.core.state import CareerState
from backend.services.llm_service import ModelRouter, TaskCategory
from backend.services.market_analyzer import analyze_market
from backend.services.skill_gap_engine import analyze_skill_gaps

logger = logging.getLogger(__name__)

_router = ModelRouter()

# ── Single comprehensive prompt for the entire roadmap ──────────────────────

_FULL_ROADMAP_PROMPT = """\
You are an expert career coach. Generate a COMPLETE, step-by-step career roadmap.

Target role: {target_role}

User's current skills: {current_skills}
Skill gaps to fill: {gap_skills}

Return a JSON object with exactly these keys:
{{
  "roadmap_steps": [
    {{
      "step": 1,
      "title": "Learn Python",
      "duration": "3-4 weeks",
      "topics": ["Variables & Data Types", "Functions & OOP", "File I/O", "Libraries overview"],
      "resources": ["Python.org tutorial", "Automate the Boring Stuff"],
      "practice": "Build a CLI tool that parses CSV files"
    }}
  ],
  "portfolio_projects": [
    {{
      "name": "Project Name",
      "difficulty": "beginner/intermediate/advanced",
      "description": "What you'll build",
      "skills_practiced": ["skill1", "skill2"],
      "technologies": ["tech1", "tech2"],
      "estimated_time": "2-3 weeks"
    }}
  ],
  "application_strategy": {{
    "resume_tips": ["tip1", "tip2"],
    "portfolio_tips": ["tip1", "tip2"],
    "networking": ["tip1", "tip2"],
    "job_search": ["tip1", "tip2"]
  }}
}}

Rules for roadmap_steps:
- Include 5-8 steps, ordered from fundamentals to advanced
- Each step must have 3-6 specific topics (not generic)
- Each step must have 1-2 concrete resources (course names, book titles, tutorial URLs)
- Each step must have a hands-on practice project
- For ML Engineer: start with Python → Math/Calculus → Statistics → ML Libraries → Deep Learning → Specialization → Portfolio
- Be SPECIFIC to the target role, not generic

Rules for portfolio_projects:
- Include 3 projects, increasing difficulty
- Each must have a clear description and technologies used
- Start with a small data analysis project, end with a full end-to-end ML pipeline

Rules for application_strategy:
- 3-4 specific tips per category
- Tips should be actionable, not generic
- Include specific platforms (LinkedIn, GitHub, Kaggle, etc.)

Return ONLY valid JSON, no markdown fences.
"""


async def generate_full_roadmap_node(state: CareerState) -> dict:
    """Single LLM call that generates the entire career roadmap."""
    target_role = state.get("target_role", "software engineer")
    profile_data = state.get("resume_profile", {})
    gaps = state.get("skill_gaps", [])

    # Build current skills summary
    resume_skills = [
        s.get("name", "")
        for s in profile_data.get("skills", [])
        if isinstance(s, dict) and s.get("name")
    ]
    current_skills = ", ".join(resume_skills[:15]) if resume_skills else "No skills detected"

    # Build gap summary
    gap_skills = ", ".join(
        g.get("skill", "") for g in gaps if isinstance(g, dict) and g.get("skill")
    ) or "Python, core libraries, domain fundamentals"

    prompt = _FULL_ROADMAP_PROMPT.format(
        target_role=target_role,
        current_skills=current_skills,
        gap_skills=gap_skills,
    )

    try:
        result = await _router.complete(
            messages=[{"role": "user", "content": prompt}],
            category=TaskCategory.CAREER_STRATEGY,
            model="fast",  # Use fast model for speed
        )
        raw = str(result)
        roadmap_data = _parse_roadmap_json(raw)
    except Exception as exc:
        logger.warning("LLM roadmap failed, using fallback: %s", exc)
        roadmap_data = _fallback_roadmap(target_role, resume_skills, gap_skills)

    plan = state.get("plan", {})
    return {"plan": {**plan, **roadmap_data}}


def _parse_roadmap_json(raw: str) -> dict:
    """Parse LLM JSON response into structured roadmap data."""
    # Try direct JSON parse first
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        pass

    # Try extracting JSON from markdown fences
    if "```" in raw:
        lines = raw.splitlines()
        json_lines = []
        in_fence = False
        for line in lines:
            if line.strip().startswith("```"):
                in_fence = not in_fence
                continue
            if in_fence:
                json_lines.append(line)
        if json_lines:
            try:
                return json.loads("\n".join(json_lines))
            except (json.JSONDecodeError, TypeError):
                pass

    # Try finding JSON object in text
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(raw[start : end + 1])
        except (json.JSONDecodeError, TypeError):
            pass

    return {}


def _fallback_roadmap(target_role: str, skills: list[str], gap_str: str) -> dict:
    """Deterministic fallback when LLM is unavailable."""
    role_lower = target_role.lower()

    # Role-specific roadmap steps
    if any(kw in role_lower for kw in ("ml", "machine learning", "data scien", "ai")):
        steps = [
            {"step": 1, "title": "Master Python Programming", "duration": "3-4 weeks",
             "topics": ["Variables, Data Types, Control Flow", "Functions & OOP", "File I/O & Error Handling", "List/Dict Comprehensions", "Virtual Environments & pip"],
             "resources": ["Automate the Boring Stuff with Python", "Python.org Official Tutorial"],
             "practice": "Build a CLI tool that reads CSV data and performs calculations"},
            {"step": 2, "title": "Mathematics for ML", "duration": "3-4 weeks",
             "topics": ["Linear Algebra (Vectors, Matrices, Eigenvalues)", "Calculus (Derivatives, Gradients, Chain Rule)", "Probability & Statistics", "Optimization Methods"],
             "resources": ["3Blue1Brown Essence of Linear Algebra", "Khan Academy Calculus", "StatQuest YouTube"],
             "practice": "Implement gradient descent from scratch in NumPy"},
            {"step": 3, "title": "Data Analysis & Visualization", "duration": "2-3 weeks",
             "topics": ["NumPy Arrays & Operations", "Pandas DataFrames", "Matplotlib & Seaborn Plotting", "Exploratory Data Analysis (EDA)", "Data Cleaning Techniques"],
             "resources": ["Kaggle Learn - Pandas", "Python for Data Analysis (Wes McKinney)"],
             "practice": "Analyze a real-world dataset and create 10+ visualizations"},
            {"step": 4, "title": "Machine Learning Fundamentals", "duration": "4-5 weeks",
             "topics": ["Supervised Learning (Regression, Classification)", "Unsupervised Learning (Clustering, PCA)", "Model Evaluation & Cross-Validation", "Feature Engineering", "Scikit-learn Pipeline"],
             "resources": ["Andrew Ng's ML Course (Coursera)", "Hands-On ML with Scikit-Learn (Aurélien Géron)"],
             "practice": "Build an end-to-end ML pipeline on Kaggle"},
            {"step": 5, "title": "Deep Learning & Neural Networks", "duration": "4-5 weeks",
             "topics": ["Neural Network Architecture", "Backpropagation & Gradient Descent", "CNNs for Computer Vision", "RNNs/Transformers for NLP", "Transfer Learning"],
             "resources": ["fast.ai Practical Deep Learning", "Deep Learning Specialization (Andrew Ng)"],
             "practice": "Fine-tune a pre-trained model on a custom dataset"},
            {"step": 6, "title": "MLOps & Production", "duration": "3-4 weeks",
             "topics": ["Model Serving (FastAPI, Docker)", "Experiment Tracking (MLflow)", "Data Pipelines (Airflow)", "Model Monitoring", "Cloud Deployment (AWS/GCP)"],
             "resources": ["Made With ML (Goku Mohandas)", "Full Stack Deep Learning"],
             "practice": "Deploy a model as a REST API with Docker and monitoring"},
            {"step": 7, "title": "Specialization & Portfolio", "duration": "3-4 weeks",
             "topics": ["Choose a domain (NLP, CV, RecSys)", "Advanced techniques in your domain", "Kaggle competitions", "Open source contributions", "Technical blog writing"],
             "resources": ["Kaggle Competitions", "Papers With Code"],
             "practice": "Build and deploy a complete ML project with documentation"},
        ]
    else:
        steps = [
            {"step": 1, "title": f"Core Fundamentals for {target_role}", "duration": "3-4 weeks",
             "topics": ["Programming basics", "Version control (Git)", "Command line", "IDE setup"],
             "resources": ["Official documentation", "FreeCodeCamp"],
             "practice": "Set up your development environment"},
            {"step": 2, "title": "Intermediate Skills", "duration": "4-5 weeks",
             "topics": ["Data structures", "Algorithms", "System design basics", "Testing"],
             "resources": ["LeetCode", "Cracking the Coding Interview"],
             "practice": "Solve 20+ coding challenges"},
            {"step": 3, "title": "Advanced Topics", "duration": "4-5 weeks",
             "topics": ["Design patterns", "APIs & databases", "Performance optimization", "Security"],
             "resources": ["Designing Data-Intensive Applications", "System Design Interview"],
             "practice": "Build a full-stack project"},
        ]

    projects = [
        {"name": f"{target_role} Starter Project", "difficulty": "beginner",
         "description": "A foundational project demonstrating core skills", "skills_practiced": skills[:3] or ["programming"],
         "technologies": ["Python"], "estimated_time": "2 weeks"},
        {"name": f"{target_role} Intermediate Project", "difficulty": "intermediate",
         "description": "A more complex project with multiple components", "skills_practiced": skills[:4] or ["programming", "databases"],
         "technologies": ["Python", "SQL"], "estimated_time": "3-4 weeks"},
        {"name": f"{target_role} Portfolio Capstone", "difficulty": "advanced",
         "description": "A production-quality project for your portfolio", "skills_practiced": skills[:5] or ["full stack"],
         "technologies": ["Python", "Docker", "Cloud"], "estimated_time": "4-6 weeks"},
    ]

    return {
        "roadmap_steps": steps,
        "portfolio_projects": projects,
        "application_strategy": {
            "resume_tips": [
                "Tailor your resume for each application with relevant keywords",
                "Quantify achievements with metrics (e.g., 'improved accuracy by 15%')",
                "Keep it to 1-2 pages with clear, concise bullet points",
            ],
            "portfolio_tips": [
                "Host all projects on GitHub with README documentation",
                "Deploy live demos where possible",
                "Write blog posts explaining your technical decisions",
            ],
            "networking": [
                "Attend local meetups and tech conferences",
                "Engage on LinkedIn with thoughtful comments",
                "Contribute to open-source projects in your field",
            ],
            "job_search": [
                "Apply to 5-10 jobs daily with customized applications",
                "Use LinkedIn, Indeed, and company career pages",
                "Reach out to recruiters and hiring managers directly",
            ],
        },
    }


# ── Analyze nodes (deterministic, no LLM) ──────────────────────────────────


async def analyze_current_state_node(state: CareerState) -> dict:
    """Analyze the user's current career position from their resume profile."""
    profile_data = state.get("resume_profile", {})

    summary_parts = []
    if profile_data.get("skills"):
        skill_names = [s.get("name", "") for s in profile_data["skills"] if isinstance(s, dict)]
        summary_parts.append(f"Skills: {', '.join(skill_names[:15])}")

    if profile_data.get("experience"):
        exp = profile_data["experience"]
        summary_parts.append(f"Experience entries: {len(exp)}")
        if exp:
            latest = exp[0] if isinstance(exp[0], dict) else {}
            summary_parts.append(f"Current/Recent role: {latest.get('title', 'N/A')}")

    if profile_data.get("years_experience"):
        summary_parts.append(f"Years: {profile_data['years_experience']}")

    if profile_data.get("education"):
        summary_parts.append(f"Education: {len(profile_data['education'])} entries")

    return {"market_data": {"_current_state_summary": "\n".join(summary_parts)}}


async def analyze_market_node(state: CareerState) -> dict:
    """Analyze market data for the target role."""
    target_role = state.get("target_role", "")
    market = analyze_market(jobs=[], target_role=target_role)
    return {"market_data": {**market.model_dump(), "_target_role": target_role}}


async def identify_gaps_node(state: CareerState) -> dict:
    """Identify skill gaps between resume and target role."""
    profile_data = state.get("resume_profile", {})
    market_data = state.get("market_data", {})

    resume_skills = [
        s.get("name", "")
        for s in profile_data.get("skills", [])
        if isinstance(s, dict)
    ]
    role_skills = list(market_data.get("skill_frequency", {}).keys())[:20]
    market_skills = market_data.get("skill_frequency", {})

    gaps = analyze_skill_gaps(resume_skills, role_skills, market_skills)
    return {"skill_gaps": [gap.model_dump() for gap in gaps]}


# ── Synthesize final plan ──────────────────────────────────────────────────


async def synthesize_plan_node(state: CareerState) -> dict:
    """Assemble the final CareerPlan from all computed components."""
    plan_data = state.get("plan", {})
    gaps = state.get("skill_gaps", [])
    market = state.get("market_data", {})

    career_plan = CareerPlan(
        current_state=market.get("_current_state_summary", ""),
        target_state=f"Master {state.get('target_role', 'target field')}",
        skill_gaps=[SkillGap(**g) for g in gaps if isinstance(g, dict)],
        learning_priorities=[s.get("title", "") for s in plan_data.get("roadmap_steps", [])],
        timeline={},
        interview_prep="",
        application_strategy="",
    )

    plan_dict = career_plan.model_dump()

    # Attach the full roadmap data for frontend rendering
    if plan_data.get("roadmap_steps"):
        plan_dict["roadmap_steps"] = plan_data["roadmap_steps"]
    if plan_data.get("portfolio_projects"):
        plan_dict["portfolio_projects"] = plan_data["portfolio_projects"]
    if plan_data.get("application_strategy"):
        plan_dict["application_strategy"] = plan_data["application_strategy"]

    logger.info(
        "Career plan synthesized: %d skill gaps, %d roadmap steps, target=%s",
        len(career_plan.skill_gaps),
        len(plan_data.get("roadmap_steps", [])),
        state.get("target_role"),
    )

    return {"plan": plan_dict}


async def error_node(state: CareerState) -> dict:
    """Handle pipeline errors."""
    logger.error("Career pipeline failed for user=%s", state.get("user_id"))
    return {"plan": CareerPlan().model_dump()}


# ── Routing ───────────────────────────────────────────────────────────────────


def route_after_gaps(state: CareerState) -> str:
    return "generate_full_roadmap"


# ── Graph ──────────────────────────────────────────────────────────────────────


def build_career_graph() -> StateGraph:
    """Construct the career planning workflow — optimized single-call pipeline."""
    graph = StateGraph(CareerState)

    graph.add_node("analyze_current_state", analyze_current_state_node)
    graph.add_node("analyze_market", analyze_market_node)
    graph.add_node("identify_gaps", identify_gaps_node)
    graph.add_node("generate_full_roadmap", generate_full_roadmap_node)
    graph.add_node("synthesize_plan", synthesize_plan_node)
    graph.add_node("error_node", error_node)

    graph.add_edge(START, "analyze_current_state")
    graph.add_edge("analyze_current_state", "analyze_market")
    graph.add_edge("analyze_market", "identify_gaps")
    graph.add_conditional_edges(
        "identify_gaps",
        route_after_gaps,
        {"generate_full_roadmap": "generate_full_roadmap", "error_node": "error_node"},
    )
    graph.add_edge("generate_full_roadmap", "synthesize_plan")
    graph.add_edge("synthesize_plan", END)
    graph.add_edge("error_node", END)

    return graph


# Compiled graph instance
career_pipeline = build_career_graph().compile()
