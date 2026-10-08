"""Placeholder projects: section must never disappear, skills must never be invented."""

from backend.services.docx_builder import _dummy_projects, build_resume_docx


def demo():
    # Fewer than 2 skills -> nothing can be honestly built
    assert _dummy_projects([]) == []
    assert _dummy_projects(["Python"]) == []

    skills = ["Python", "SQL", "LangGraph", "FastAPI", "Docker"]
    projects = _dummy_projects(skills)
    assert len(projects) == 3, len(projects)
    for p in projects:
        assert p["name"] and p["description"] and p["bullets"]
        # Only the candidate's own skills may appear as technologies
        assert set(p["technologies"]) <= set(skills), p["technologies"]

    # Two-skill resumes get 2 projects, not a crash
    assert len(_dummy_projects(["Python", "SQL"])) == 2

    # Empty projects in the data -> section still renders
    data = build_resume_docx({
        "contact": {"name": "Test User"},
        "skills": skills,
        "projects": [],
    })
    from docx import Document
    import io
    text = "\n".join(p.text for p in Document(io.BytesIO(data)).paragraphs)
    assert "Technical Projects" in text, "missing Projects section"
    print("OK")


if __name__ == "__main__":
    demo()
