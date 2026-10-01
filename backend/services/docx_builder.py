"""DOCX generation for tailored resumes.

Builds a clean, ATS-friendly Word document from an ``OptimizedResume``.
Uses python-docx (already a project dependency for resume parsing).
"""

from __future__ import annotations

import io
import logging
import re

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

logger = logging.getLogger(__name__)

# Brand palette (mirrors frontend --accent-primary)
ACCENT = RGBColor(0x2E, 0x9E, 0x6E)
HEADING = RGBColor(0x11, 0x18, 0x27)
BODY = RGBColor(0x37, 0x41, 0x51)
MUTED = RGBColor(0x6B, 0x72, 0x80)

FONT = "Calibri"


# ── Low-level XML helpers ────────────────────────────────────────────────────


def _set_paragraph_border(paragraph, *, color: str = "2E9E6E", size: int = 8) -> None:
    """Draw a thin rule beneath the paragraph."""
    p_pr = paragraph._p.get_or_add_pPr()
    borders = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), str(size))
    bottom.set(qn("w:space"), "2")
    bottom.set(qn("w:color"), color)
    borders.append(bottom)
    p_pr.append(borders)


def _set_cell_shading(paragraph, fill: str) -> None:
    p_pr = paragraph._p.get_or_add_pPr()
    shading = OxmlElement("w:shd")
    shading.set(qn("w:val"), "clear")
    shading.set(qn("w:color"), "auto")
    shading.set(qn("w:fill"), fill)
    p_pr.append(shading)


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
    _tighten(p, before=10, after=5)
    _add_run(p, title.upper(), size=11, bold=True, color=ACCENT)
    _set_paragraph_border(p, color="2E9E6E", size=6)
    return p


def _bullet(doc: Document, text: str, *, level: int = 0) -> None:
    text = (text or "").strip()
    if not text:
        return
    p = doc.add_paragraph()
    _tighten(p, before=0, after=2, line=1.08)
    p.paragraph_format.left_indent = Inches(0.22 + 0.2 * level)
    p.paragraph_format.first_line_indent = Inches(-0.18)
    _add_run(p, "\u25aa  ", size=10, color=ACCENT, bold=True)
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


def _join_contact(parts: list[str]) -> str:
    cleaned = [p.strip() for p in parts if p and str(p).strip()]
    return "   \u2022   ".join(cleaned)


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


# ── Public API ──────────────────────────────────────────────────────────────


def build_resume_docx(resume: dict, *, page_width: float = 8.27) -> bytes:
    """Render an ``OptimizedResume`` dict into DOCX bytes.

    ``page_width`` defaults to A4 (8.27in); pass ``8.5`` for US Letter.
    Never raises: every section is rendered defensively so a single odd value
    cannot break the download.
    """
    resume = _as_dict(resume)
    doc = Document()

    # Page setup
    section = doc.sections[0]
    section.top_margin = Inches(0.6)
    section.bottom_margin = Inches(0.55)
    section.left_margin = Inches(0.7)
    section.right_margin = Inches(0.7)
    usable = page_width - 1.4

    # Normal style defaults
    normal = doc.styles["Normal"]
    normal.font.name = FONT
    normal.font.size = Pt(10)
    normal.paragraph_format.space_after = Pt(0)

    contact = _as_dict(resume.get("contact"))
    name = _txt(contact.get("name")).strip()

    # ── Header: name + headline ─────────────────────────────────────────────
    def _header() -> None:
        if name:
            p = doc.add_paragraph()
            _tighten(p, before=0, after=1)
            _add_run(p, name, size=20, bold=True, color=HEADING)

        headline = _txt(resume.get("headline") or resume.get("target_role")).strip()
        if headline:
            p = doc.add_paragraph()
            _tighten(p, before=0, after=4)
            _add_run(p, headline, size=11.5, bold=True, color=ACCENT)

        contact_line = _join_contact([
            _txt(contact.get("email")),
            _txt(contact.get("phone")),
            _txt(contact.get("linkedin")),
            _txt(contact.get("github")),
            _txt(contact.get("website")),
        ])
        if contact_line:
            p = doc.add_paragraph()
            _tighten(p, before=0, after=6)
            _add_run(p, contact_line, size=9, color=MUTED)
            _set_paragraph_border(p, color="D1D5DB", size=6)

    _safe("header", _header)

    # ── Summary ─────────────────────────────────────────────────────────────
    def _summary_section() -> None:
        summary = _txt(resume.get("summary")).strip()
        if summary:
            _section_heading(doc, "Professional Summary")
            _plain(doc, summary)

    _safe("summary", _summary_section)

    # ── Skills ──────────────────────────────────────────────────────────────
    def _skills_section() -> None:
        skills = [_txt(s).strip() for s in _as_list(resume.get("skills"))]
        skills = [s for s in skills if s]
        if skills:
            _section_heading(doc, "Skills")
            _plain(doc, "  \u2022  ".join(skills))

    _safe("skills", _skills_section)

    # ── Experience ──────────────────────────────────────────────────────────
    def _experience_section() -> None:
        experience = _as_list(resume.get("experience"))
        if not experience:
            return
        _section_heading(doc, "Professional Experience")
        for raw_exp in experience:
            exp = _as_dict(raw_exp)
            title = _txt(exp.get("title")).strip()
            company = _txt(exp.get("company")).strip()
            location = _txt(exp.get("location")).strip()
            dates = _date_range(
                _txt(exp.get("start_date")), _txt(exp.get("end_date")),
                bool(exp.get("is_current")),
            )

            p = doc.add_paragraph()
            _tighten(p, before=7, after=1)
            # Right-aligned date stop at the right margin
            p.paragraph_format.tab_stops.add_tab_stop(
                Inches(usable), WD_TAB_ALIGNMENT.RIGHT
            )
            left = " \u2014 ".join(x for x in (title, company) if x)
            if not left:
                left = title or company
            if not left:
                continue
            _add_run(p, left, size=10.5, bold=True, color=HEADING)
            if dates:
                _add_run(p, "\t" + dates, size=9, italic=True, color=MUTED)

            if location:
                lp = doc.add_paragraph()
                _tighten(lp, before=0, after=2)
                _add_run(lp, location, size=9, italic=True, color=MUTED)

            for raw_bullet in _as_list(exp.get("bullets")):
                _bullet(doc, _txt(raw_bullet))

    _safe("experience", _experience_section)

    # ── Projects ────────────────────────────────────────────────────────────
    def _projects_section() -> None:
        projects = _as_list(resume.get("projects"))
        if not projects:
            return
        _section_heading(doc, "Projects")
        for raw_proj in projects:
            proj = _as_dict(raw_proj)
            pname = _txt(proj.get("name")).strip()
            if not pname:
                continue
            p = doc.add_paragraph()
            _tighten(p, before=6, after=1)
            _add_run(p, pname, size=10.5, bold=True, color=HEADING)
            techs = ", ".join(
                t for t in (_txt(x).strip() for x in _as_list(proj.get("technologies"))) if t
            )
            if techs:
                _add_run(p, f"  \u2014  {techs}", size=9, italic=True, color=ACCENT)
            desc = _txt(proj.get("description")).strip()
            if desc:
                _plain(doc, desc, after=1)
            for raw_bullet in _as_list(proj.get("bullets")):
                _bullet(doc, _txt(raw_bullet))

    _safe("projects", _projects_section)

    # ── Education ───────────────────────────────────────────────────────────
    def _education_section() -> None:
        education = _as_list(resume.get("education"))
        if not education:
            return
        _section_heading(doc, "Education")
        for raw_edu in education:
            edu = _as_dict(raw_edu)
            institution = _txt(edu.get("institution")).strip()
            degree = _txt(edu.get("degree")).strip()
            field = _txt(edu.get("field")).strip()
            if not institution and not degree:
                continue
            gpa = _txt(edu.get("gpa")).strip()

            p = doc.add_paragraph()
            _tighten(p, before=5, after=1)
            p.paragraph_format.tab_stops.add_tab_stop(
                Inches(usable), WD_TAB_ALIGNMENT.RIGHT
            )
            left = " \u2014 ".join(x for x in (degree, field) if x)
            label = " \u2014 ".join(x for x in (left, institution) if x)
            _add_run(p, label, size=10.5, bold=True, color=HEADING)

            dates = _date_range(_txt(edu.get("start_date")), _txt(edu.get("end_date")), False)
            right = dates or (f"GPA: {gpa}" if gpa else "")
            if right:
                _add_run(p, "\t" + right, size=9, italic=True, color=MUTED)

    _safe("education", _education_section)

    # ── Certifications ──────────────────────────────────────────────────────
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

    # ── Footer note ─────────────────────────────────────────────────────────
    def _footer() -> None:
        fp = doc.add_paragraph()
        _tighten(fp, before=12, after=0)
        fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        target = _txt(resume.get("target_role")).strip()
        company = _txt(resume.get("target_company")).strip()
        tail = f"for the {target} role" if target else ""
        if company:
            tail += f" at {company}"
        _add_run(
            fp,
            f"Resume optimized {tail}" if tail else "Optimized resume",
            size=8, italic=True, color=MUTED,
        )

    _safe("footer", _footer)

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
