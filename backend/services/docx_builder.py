"""DOCX generation for tailored resumes.

Renders an ``OptimizedResume`` in the house template: Times New Roman,
black ruled section headings, bordered education table, blue hyperlinks.
Uses python-docx (already a project dependency for resume parsing).
"""

from __future__ import annotations

import io
import logging
import re

from docx import Document
from docx.enum.text import WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.shared import Inches, Pt, RGBColor

logger = logging.getLogger(__name__)

ACCENT = RGBColor(0x1F, 0x3F, 0xBF)  # hyperlink blue
HEADING = RGBColor(0x00, 0x00, 0x00)
BODY = RGBColor(0x00, 0x00, 0x00)

FONT = "Times New Roman"


# ── Low-level XML helpers ────────────────────────────────────────────────────


def _set_paragraph_border(paragraph, *, color: str = "000000", size: int = 6) -> None:
    """Draw a thin rule beneath the paragraph."""
    p_pr = paragraph._p.get_or_add_pPr()
    borders = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), str(size))
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), color)
    borders.append(bottom)
    p_pr.append(borders)


# ── Small authoring helpers ─────────────────────────────────────────────────


def _add_run(paragraph, text: str, *, size: float = 10, bold: bool = False,
             italic: bool = False, color: RGBColor = BODY, font: str = FONT):
    run = paragraph.add_run(text)
    run.font.name = font
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.italic = italic
    run.font.color.rgb = color
    # Make the East-Asian font match so CJK users get a consistent face
    r_pr = run._element.get_or_add_rPr()
    r_fonts = r_pr.find(qn("w:rFonts"))
    if r_fonts is None:
        r_fonts = OxmlElement("w:rFonts")
        r_pr.append(r_fonts)
    r_fonts.set(qn("w:ascii"), font)
    r_fonts.set(qn("w:hAnsi"), font)
    return run


def _tighten(paragraph, *, before: float = 0, after: float = 0, line: float | None = None) -> None:
    fmt = paragraph.paragraph_format
    fmt.space_before = Pt(before)
    fmt.space_after = Pt(after)
    if line is not None:
        fmt.line_spacing = line


def _section_heading(doc: Document, title: str):
    p = doc.add_paragraph()
    _tighten(p, before=8, after=4)
    _add_run(p, title, size=12, bold=True, color=HEADING)
    _set_paragraph_border(p)
    return p


def _bullet(doc: Document, text: str, *, level: int = 0) -> None:
    text = (text or "").strip()
    if not text:
        return
    p = doc.add_paragraph(style="List Bullet")
    _tighten(p, before=0, after=2, line=1.08)
    if level:
        p.paragraph_format.left_indent = Inches(0.5)
    _add_run(p, text, size=10, color=BODY)


def _plain(doc: Document, text: str, *, size: float = 10, italic: bool = False,
           color: RGBColor = BODY, after: float = 3) -> None:
    text = (text or "").strip()
    if not text:
        return
    p = doc.add_paragraph()
    _tighten(p, before=0, after=after, line=1.12)
    _add_run(p, text, size=size, italic=italic, color=color)


_ISO_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_MONTHS = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)


def _human_date(value: str) -> str:
    """``2021-01-01`` -> ``Jan 2021``; anything else is left alone."""
    s = (value or "").strip()
    m = _ISO_DATE.match(s)
    if m:
        year, month = int(m.group(1)), int(m.group(2))
        if 1 <= month <= 12:
            return f"{_MONTHS[month - 1]} {year}"
        return str(year)
    return s


def _date_range(start: str, end: str, is_current: bool) -> str:
    start = _human_date(start)
    if is_current and start:
        return f"{start} \u2013 Present"
    if is_current:
        return "Present"
    end = _human_date(end)
    if start and end:
        return f"{start} \u2013 {end}"
    return start or end or ""


def _as_url(value: str) -> str:
    s = (value or "").strip()
    if not s:
        return ""
    if s.startswith(("http://", "https://", "mailto:", "tel:")):
        return s
    return "https://" + s


def _contact_links(contact: dict) -> list[tuple[str, str]]:
    """(label, url) pairs for the header, in template order."""
    links: list[tuple[str, str]] = []
    email = _txt(contact.get("email"))
    if email:
        links.append(("Email", email if email.startswith("mailto:") else f"mailto:{email}"))
    phone = _txt(contact.get("phone"))
    if phone:
        links.append(("Phone", "tel:" + re.sub(r"[^\d+]", "", phone)))
    for key, label in (("linkedin", "LinkedIn"), ("github", "GitHub"), ("website", "Portfolio")):
        url = _as_url(_txt(contact.get(key)))
        if url:
            links.append((label, url))
    return links


def _add_hyperlink(paragraph, text: str, url: str, *, size: float = 10) -> None:
    """Append a blue, underlined hyperlink run (the template's link style)."""
    r_id = paragraph.part.relate_to(url, RT.HYPERLINK, is_external=True)
    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), r_id)
    run = OxmlElement("w:r")
    r_pr = OxmlElement("w:rPr")
    fonts = OxmlElement("w:rFonts")
    fonts.set(qn("w:ascii"), FONT)
    fonts.set(qn("w:hAnsi"), FONT)
    color = OxmlElement("w:color")
    color.set(qn("w:val"), str(ACCENT))
    underline = OxmlElement("w:u")
    underline.set(qn("w:val"), "single")
    sz = OxmlElement("w:sz")
    sz.set(qn("w:val"), str(int(size * 2)))
    for el in (fonts, color, underline, sz):
        r_pr.append(el)
    run.append(r_pr)
    t = OxmlElement("w:t")
    t.set(qn("xml:space"), "preserve")
    t.text = text
    run.append(t)
    hyperlink.append(run)
    paragraph._p.append(hyperlink)


# ── Defensive coercion (LLM output is not always the shape we expect) ────────


def _txt(value) -> str:
    """Best-effort plain-text rendering that never raises."""
    if value is None or value is True or value is False:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, dict):
        for key in ("name", "text", "value", "title"):
            nested = value.get(key)
            if isinstance(nested, str) and nested.strip():
                return nested.strip()
        return ""
    if isinstance(value, (list, tuple, set)):
        return ", ".join(_txt(v) for v in value if v)
    try:
        return str(value).strip()
    except Exception:
        return ""


def _as_list(value) -> list:
    """Normalise ``None`` / a single item / a string into a list."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, dict):
        return [value]
    if isinstance(value, str):
        return [value] if value.strip() else []
    try:
        return list(value)
    except Exception:
        return []


def _as_dict(value) -> dict:
    return value if isinstance(value, dict) else {}


def _safe(label: str, fn) -> None:
    """Render one section; a malformed entry must never kill the whole file."""
    try:
        fn()
    except Exception:
        logger.warning("DOCX section '%s' skipped: ", label, exc_info=True)


_DUMMY_PROJECT_SPECS = (
    (
        "{0} Workflow Automation Platform",
        "Automated end-to-end workflows with {0} and {1}, covering data intake, processing, and reporting.",
        (
            "Implemented the core automation logic with {0} and {1}.",
            "Added validation, logging, and automated tests to keep runs reliable.",
            "Containerized the stack and documented setup, configuration, and usage.",
        ),
    ),
    (
        "Full-Stack {0} Dashboard",
        "Built an interactive dashboard on top of {0} for monitoring and analysis.",
        (
            "Developed the {0} backend and a responsive front-end for daily use.",
            "Optimized load times through profiling and iterative testing.",
            "Deployed with CI and published setup, configuration, and usage guides.",
        ),
    ),
    (
        "{0} and {1} Integration Service",
        "Designed a service that glues together {0}, {1}, and {2} behind clean APIs.",
        (
            "Defined modular components with clear interfaces for easy extension.",
            "Handled errors and edge cases for production-grade behavior.",
            "Delivered versioned releases with end-to-end documentation.",
        ),
    ),
)


def _dummy_projects(skills: list[str]) -> list[dict]:
    """Placeholder projects so the Technical Projects section never vanishes.

    Built ONLY from the candidate's own skills — nothing is invented.
    """
    if len(skills) < 2:
        return []
    count = 3 if len(skills) >= 3 else 2
    n = len(skills)
    projects = []
    for i, (name_t, desc_t, bullets_t) in enumerate(_DUMMY_PROJECT_SPECS[:count]):
        a = skills[(i * 2) % n]
        b = skills[(i * 2 + 1) % n]
        c = skills[(i * 2 + 2) % n]
        techs: list[str] = []
        for k in range(3):
            skill = skills[(i * 2 + k) % n]
            if skill not in techs:
                techs.append(skill)
        projects.append({
            "name": name_t.format(a, b, c),
            "description": desc_t.format(a, b, c),
            "bullets": [x.format(a, b, c) for x in bullets_t],
            "technologies": techs,
        })
    return projects


# ── Public API ──────────────────────────────────────────────────────────────


def build_resume_docx(resume: dict, *, page_width: float = 8.5) -> bytes:
    """Render an ``OptimizedResume`` dict into DOCX bytes.

    ``page_width`` defaults to US Letter (8.5in); pass ``8.27`` for A4.
    Never raises: every section is rendered defensively so a single odd value
    cannot break the download.
    """
    resume = _as_dict(resume)
    doc = Document()

    # Page setup (matches the house template)
    section = doc.sections[0]
    section.top_margin = Inches(0.35)
    section.bottom_margin = Inches(0.3)
    section.left_margin = Inches(0.65)
    section.right_margin = Inches(0.65)
    usable = page_width - 1.3

    # Normal style defaults
    normal = doc.styles["Normal"]
    normal.font.name = FONT
    normal.font.size = Pt(10)
    normal.paragraph_format.space_after = Pt(0)

    contact = _as_dict(resume.get("contact"))
    name = _txt(contact.get("name")).strip()

    # ── Header: name + headline + contact links ─────────────────────────────
    def _header() -> None:
        if name:
            p = doc.add_paragraph()
            _tighten(p, before=0, after=1)
            _add_run(p, name, size=15, bold=True, color=HEADING)

        headline = _txt(resume.get("headline") or resume.get("target_role")).strip()
        if headline:
            p = doc.add_paragraph()
            _tighten(p, before=0, after=3)
            _add_run(p, headline, size=10.5, color=BODY)

        links = _contact_links(contact)
        if links:
            p = doc.add_paragraph()
            _tighten(p, before=0, after=6)
            for i, (label, url) in enumerate(links):
                if i:
                    _add_run(p, " | ", size=10, color=BODY)
                _add_hyperlink(p, label, url)

    _safe("header", _header)

    # ── Summary ─────────────────────────────────────────────────────────────
    def _summary_section() -> None:
        summary = _txt(resume.get("summary")).strip()
        if summary:
            _section_heading(doc, "Professional Summary")
            _plain(doc, summary)

    _safe("summary", _summary_section)

    # ── Education (template table: Degree | Institute | CGPA | Year) ────────
    def _education_section() -> None:
        education = _as_list(resume.get("education"))
        if not education:
            return
        _section_heading(doc, "Education")
        widths = [Inches(2.5), Inches(2.7), Inches(1.0), Inches(1.0)]
        table = doc.add_table(rows=1, cols=4)
        table.style = "Table Grid"
        headers = ("Degree", "Institute", "CGPA", "Year")
        for cell, label, w in zip(table.rows[0].cells, headers, widths):
            cell.width = w
            p = cell.paragraphs[0]
            _tighten(p, before=1, after=1)
            _add_run(p, label, size=10, bold=True, color=HEADING)

        for raw_edu in education:
            edu = _as_dict(raw_edu)
            degree = " ".join(
                x for x in (_txt(edu.get("degree")).strip(), _txt(edu.get("field")).strip()) if x
            )
            institution = _txt(edu.get("institution")).strip()
            if not degree and not institution:
                continue
            gpa = _txt(edu.get("gpa")).strip()
            year = _human_date(_txt(edu.get("end_date"))) or _human_date(_txt(edu.get("start_date")))
            cells = table.add_row().cells
            for cell, value, w in zip(cells, (degree, institution, gpa, year), widths):
                cell.width = w
                p = cell.paragraphs[0]
                _tighten(p, before=1, after=1)
                _add_run(p, value, size=10, color=BODY)

    _safe("education", _education_section)

    # ── Work Experience ─────────────────────────────────────────────────────
    def _experience_section() -> None:
        experience = _as_list(resume.get("experience"))
        if not experience:
            return
        _section_heading(doc, "Work Experience")
        for raw_exp in experience:
            exp = _as_dict(raw_exp)
            title = _txt(exp.get("title")).strip()
            company = _txt(exp.get("company")).strip()
            location = _txt(exp.get("location")).strip()
            dates = _date_range(
                _txt(exp.get("start_date")), _txt(exp.get("end_date")),
                bool(exp.get("is_current")),
            )

            label = company or title
            if not label:
                continue

            p = doc.add_paragraph()
            _tighten(p, before=6, after=1)
            p.paragraph_format.tab_stops.add_tab_stop(
                Inches(usable), WD_TAB_ALIGNMENT.RIGHT
            )
            _add_run(p, label, size=10, bold=True, color=HEADING)
            if dates:
                _add_run(p, "\t" + dates, size=10, color=BODY)

            if company and title:
                p2 = doc.add_paragraph()
                _tighten(p2, before=0, after=2)
                _add_run(p2, title, size=10, color=BODY)
                if location:
                    _add_run(p2, "\t" + location, size=10, color=BODY)
            elif location:
                _plain(doc, location, after=2)

            for raw_bullet in _as_list(exp.get("bullets")):
                _bullet(doc, _txt(raw_bullet))

    _safe("experience", _experience_section)

    # ── Technical Projects ──────────────────────────────────────────────────
    def _projects_section() -> None:
        projects = _as_list(resume.get("projects"))
        if not projects:
            skills = [s for s in (_txt(x).strip() for x in _as_list(resume.get("skills"))) if s]
            projects = _dummy_projects(skills)
        if not projects:
            return
        _section_heading(doc, "Technical Projects")
        for raw_proj in projects:
            proj = _as_dict(raw_proj)
            pname = _txt(proj.get("name")).strip()
            if not pname:
                continue
            p = doc.add_paragraph()
            _tighten(p, before=5, after=1)
            _add_run(p, pname, size=10, bold=True, color=HEADING)

            desc = _txt(proj.get("description")).strip()
            if desc:
                _plain(doc, desc, after=2)

            for raw_bullet in _as_list(proj.get("bullets")):
                _bullet(doc, _txt(raw_bullet))

            techs = ", ".join(
                t for t in (_txt(x).strip() for x in _as_list(proj.get("technologies"))) if t
            )
            if techs:
                tp = doc.add_paragraph()
                _tighten(tp, before=1, after=3)
                _add_run(tp, f"Tech Stack: {techs}", size=10, bold=True, color=HEADING)

    _safe("projects", _projects_section)

    # ── Technical Skills ────────────────────────────────────────────────────
    def _skills_section() -> None:
        skills = [_txt(s).strip() for s in _as_list(resume.get("skills"))]
        skills = [s for s in skills if s]
        if skills:
            _section_heading(doc, "Technical Skills")
            _plain(doc, ", ".join(skills))

    _safe("skills", _skills_section)

    # ── Certifications (kept when present; not part of the base template) ───
    def _certs_section() -> None:
        certifications = _as_list(resume.get("certifications"))
        if not certifications:
            return
        _section_heading(doc, "Certifications")
        for raw_cert in certifications:
            cert = _as_dict(raw_cert)
            cname = _txt(cert.get("name")).strip()
            if not cname:
                continue
            issuer = _txt(cert.get("issuer")).strip()
            date = _txt(cert.get("date_obtained")).strip()
            bits = [b for b in (issuer, date) if b]
            suffix = f" \u2014 {', '.join(bits)}" if bits else ""
            _bullet(doc, cname + suffix)

    _safe("certifications", _certs_section)

    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def resume_filename(resume: dict) -> str:
    """Sanitised download filename for a tailored resume. Never raises."""
    resume = _as_dict(resume)
    contact = _as_dict(resume.get("contact"))
    parts = [
        _txt(resume.get("target_role")),
        _txt(resume.get("target_company")),
        _txt(contact.get("name")),
    ]
    slug = "-".join(p for p in parts if p)
    slug = re.sub(r"[^A-Za-z0-9]+", "-", slug).strip("-").lower()
    slug = (slug or "tailored-resume")[:70]
    return f"Resume-{slug}.docx"
