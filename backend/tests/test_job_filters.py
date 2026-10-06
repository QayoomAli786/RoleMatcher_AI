"""Self-check for job location + work-mode filtering. Run: python -m backend.tests.test_job_filters"""

import asyncio

from backend.graphs.job_graph import filter_candidates_node, _location_matches
from backend.services.job_normalizer import derive_work_mode


def _job(title, location, work_mode=None, remote=False):
    j = {"title": title, "company": "Acme", "location": location, "skills": [],
         "description": "", "remote": remote}
    if work_mode is not None:
        j["work_mode"] = work_mode
    return j


def _run(jobs, location, work_mode="any", keywords=("engineer",)):
    state = {"candidate_jobs": jobs, "query_keywords": list(keywords),
             "user_location": location, "work_mode": work_mode}
    out = asyncio.run(filter_candidates_node(state))
    return [j["title"] for j in out["candidate_jobs"]]


# ── _location_matches: normalized exact-place match ─────────────────────────

def test_location_tolerates_formatting() -> None:
    assert _location_matches("New York", "New York, NY")
    assert _location_matches("New York, NY", "New York")
    assert _location_matches("new york", "New York City, NY")


def test_location_rejects_loose_token_matches() -> None:
    assert not _location_matches("New York", "York, UK")
    assert not _location_matches("New York", "Newark, NJ")


def test_location_matches_within_region() -> None:
    assert _location_matches("California", "San Francisco, California")
    assert _location_matches("Germany", "Berlin, Germany")
    assert _location_matches("United States", "Austin, United States")


def test_location_empty_job_fails_specific_location() -> None:
    assert not _location_matches("New York", "")
    assert not _location_matches("New York", "Remote")


# ── filter matrix ───────────────────────────────────────────────────────────

def test_remote_mode_ignores_location() -> None:
    jobs = [
        _job("engineer remote", "Remote", work_mode="remote", remote=True),
        _job("engineer ny onsite", "New York, NY", work_mode="onsite"),
    ]
    assert _run(jobs, location="New York", work_mode="remote") == ["engineer remote"]


def test_onsite_mode_enforces_location_and_excludes_remote() -> None:
    jobs = [
        _job("engineer ny", "New York, NY", work_mode="onsite"),
        _job("engineer york", "York, UK", work_mode="onsite"),
        _job("engineer remote", "Anywhere", work_mode="remote", remote=True),
        _job("engineer blank", "", work_mode="onsite"),
    ]
    assert _run(jobs, location="New York", work_mode="onsite") == ["engineer ny"]


def test_hybrid_mode_only_hybrid() -> None:
    jobs = [
        _job("engineer hybrid ny", "New York, NY", work_mode="hybrid"),
        _job("engineer onsite ny", "New York, NY", work_mode="onsite"),
    ]
    assert _run(jobs, location="New York", work_mode="hybrid") == ["engineer hybrid ny"]


def test_any_mode_location_or_remote() -> None:
    jobs = [
        _job("engineer ny", "New York, NY", work_mode="onsite"),
        _job("engineer london", "London, UK", work_mode="onsite"),
        _job("engineer remote", "Anywhere", work_mode="remote", remote=True),
    ]
    assert _run(jobs, location="New York", work_mode="any") == ["engineer ny", "engineer remote"]


def test_all_countries_shows_everything() -> None:
    jobs = [
        _job("engineer ny", "New York, NY", work_mode="onsite"),
        _job("engineer london", "London, UK", work_mode="onsite"),
    ]
    assert sorted(_run(jobs, location="All Countries")) == ["engineer london", "engineer ny"]


def test_missing_work_mode_field_falls_back_to_remote_flag() -> None:
    jobs = [
        _job("engineer legacy remote", "Remote", remote=True),  # no work_mode key
        _job("engineer legacy onsite", "New York, NY"),
    ]
    assert _run(jobs, location="All Countries", work_mode="remote") == ["engineer legacy remote"]


def test_irrelevant_jobs_still_dropped() -> None:
    jobs = [_job("nurse practitioner", "New York, NY", work_mode="onsite")]
    assert _run(jobs, location="New York", work_mode="onsite") == []


# ── derive_work_mode ────────────────────────────────────────────────────────

def test_derive_work_mode() -> None:
    assert derive_work_mode("Remote - US", remote=True) == "remote"
    assert derive_work_mode("Fully Remote") == "remote"
    assert derive_work_mode("New York, NY", "Hybrid: 3 days onsite") == "hybrid"
    assert derive_work_mode("New York, NY", "Senior Engineer") == "onsite"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
    print("all checks passed")
