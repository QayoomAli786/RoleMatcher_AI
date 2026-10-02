"""Self-check for skill-alias matching. Run: python -m backend.tests.test_skill_aliases"""

from backend.core.schemas import Job, ResumeProfile, Skill, SkillCategory
from backend.services.ats_engine import calculate_ats_score
from backend.services.job_deduplicator import deduplicate
from backend.services.market_analyzer import analyze_market
from backend.services.skill_aliases import normalize_skill


def test_normalize_skill() -> None:
    assert normalize_skill("JS") == "javascript"
    assert normalize_skill("Postgres") == "postgresql"
    assert normalize_skill("sklearn") == "scikit-learn"
    assert normalize_skill("Rust") == "rust"


def test_ats_skill_score_is_alias_insensitive() -> None:
    """'js' on a resume must match 'javascript' in a job, and the reverse."""
    profile = ResumeProfile(
        skills=[
            Skill(name="js", category=SkillCategory.technical),
            Skill(name="Postgres", category=SkillCategory.technical),
        ]
    )
    job = "Looking for a developer with javascript and postgresql experience"

    report = calculate_ats_score(
        resume_text="Built web apps with js and Postgres",
        job_description=job,
        resume_profile=profile,
    )

    missing = [m.lower() for m in report.missing_skills]
    assert not any(m in {"js", "javascript", "postgres", "postgresql"} for m in missing), (
        f"alias pairs leaked into missing_skills: {report.missing_skills}"
    )
    assert report.skill_score > 0, "aliased skills must score, not read as a gap"


def test_market_analyzer_groups_aliases() -> None:
    jobs = [
        Job(title="Dev", company="A", location="Remote", description="js react", skills=["js"], source="linkedin"),
        Job(title="Dev", company="B", location="Remote", description="javascript react", skills=["javascript"], source="linkedin"),
    ]

    freq = analyze_market(jobs).skill_frequency

    assert freq.get("javascript") == 2, f"js/javascript must merge into one bucket: {freq}"
    assert "js" not in freq, f"raw alias leaked into skill_frequency: {freq}"


def test_deduplicate_merges_duplicate_fingerprints() -> None:
    jobs = [
        Job(title="Backend Engineer", company="Acme", location="Berlin", description="python", skills=["python"], source="linkedin"),
        Job(title="Backend Engineer", company="Acme", location="Berlin", description="python", skills=["python"], source="remoteok"),
    ]

    result = deduplicate(jobs)

    assert len(result) == 1, f"expected 1 unique job, got {len(result)}"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
    print("all checks passed")