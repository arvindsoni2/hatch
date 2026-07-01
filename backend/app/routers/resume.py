"""FastAPI router for master CV upload and management."""
from __future__ import annotations

import asyncio
import json
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel

from ..agents.tools.profile_loader import load_profile
from ..services.master_cv_store import invalidate_cache

router = APIRouter(prefix="/api/resume", tags=["resume"])


def _data_dir() -> Path:
    profile = load_profile()
    cv_path = Path(getattr(profile, "master_cv_path", "./data/master_cv.json"))
    if not cv_path.is_absolute():
        cv_path = Path("/app") / cv_path.relative_to(".")
    return cv_path.parent


def _cv_path() -> Path:
    profile = load_profile()
    cv_path = Path(getattr(profile, "master_cv_path", "./data/master_cv.json"))
    if not cv_path.is_absolute():
        cv_path = Path("/app") / cv_path.relative_to(".")
    return cv_path


def _meta_path() -> Path:
    return _cv_path().with_suffix(".meta.json")


# ── Parsing helpers ───────────────────────────────────────────────────────────

def _extract_text_from_docx(path: str) -> str:
    from docx import Document  # type: ignore
    doc = Document(path)
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def _extract_text_from_pdf(path: str) -> str:
    from pypdf import PdfReader  # type: ignore
    reader = PdfReader(path)
    return "\n".join(page.extract_text() or "" for page in reader.pages)


_SECTION_ALIASES: dict[str, str] = {
    "professional experience": "experience",
    "work experience": "experience",
    "employment history": "experience",
    "employment": "experience",
    "technical skills and tools": "skills",
    "technical skills": "skills",
    "skills and tools": "skills",
    "key skills": "skills",
    "core competencies": "skills",
    "competencies": "skills",
    "awards & certifications": "certifications",
    "awards and certifications": "certifications",
    "certifications and awards": "certifications",
    "qualifications": "certifications",
    "professional summary": "summary",
    "career summary": "summary",
    "executive summary": "summary",
    "personal profile": "profile",
    "contact information": "contact",
    "contact details": "contact",
}

_SECTION_RE = re.compile(
    r"^(professional experience|work experience|employment history|employment|"
    r"technical skills and tools|technical skills|skills and tools|key skills|"
    r"core competencies|competencies|skills?|"
    r"awards? & certifications?|awards? and certifications?|certifications?|"
    r"professional summary|career summary|executive summary|summary|"
    r"profile|personal profile|objective|"
    r"education|qualifications|"
    r"projects?|achievements?|publications?|references?|"
    r"contact(?: information| details)?|personal|languages?)[\s:]*$",
    re.IGNORECASE,
)


def _normalize_heading(heading: str) -> str:
    key = heading.lower().rstrip(":").strip()
    return _SECTION_ALIASES.get(key, key)


def _parse_sections(text: str) -> dict[str, Any]:
    """Heuristic section splitter — groups lines under detected headings."""
    sections: dict[str, list[str]] = {}
    current = "header"
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if _SECTION_RE.match(stripped):
            current = _normalize_heading(stripped)
            sections.setdefault(current, [])
        else:
            sections.setdefault(current, []).append(stripped)
    return {k: "\n".join(v) for k, v in sections.items() if v}


def _extract_skills(text: str) -> list[str]:
    skills_section = ""
    in_skills = False
    skill_heading = re.compile(
        r"^(technical skills.*|skills?(?: and tools)?|key skills|core competencies|competencies)[\s:]*$",
        re.IGNORECASE,
    )
    stop_heading = re.compile(
        r"^(experience|professional experience|education|employment|certifications?|awards?|"
        r"summary|profile|projects?|references?)[\s:]*$",
        re.IGNORECASE,
    )
    for line in text.splitlines():
        stripped = line.strip()
        if skill_heading.match(stripped):
            in_skills = True
            continue
        if in_skills:
            if stop_heading.match(stripped):
                break
            skills_section += " " + stripped

    raw_skills: list[str] = []
    if skills_section:
        # Split on commas, bullets, pipes, newlines — also split "Category: item1, item2"
        for chunk in re.split(r"[,|•·\n]+", skills_section):
            # Strip category labels like "Agile Delivery Tools:"
            chunk = re.sub(r"^[^:]{3,30}:\s*", "", chunk.strip())
            chunk = chunk.strip(" •·-()")
            if chunk:
                raw_skills.append(chunk)

    return [s for s in raw_skills if 1 < len(s) < 60][:60]


_DATE_RANGE_RE = re.compile(
    r"^(?P<period>(?:\d{1,2}/)?(?:19|20)\d{2}\s*[–—-]\s*"
    r"(?:Present|Current|(?:\d{1,2}/)?(?:19|20)\d{2}))\s+(?P<role>.+)$",
    re.IGNORECASE,
)


def _join_wrapped_lines(lines: list[str]) -> str:
    """Join PDF-wrapped prose while preserving intentional paragraph breaks."""
    return " ".join(line.strip() for line in lines if line.strip()).strip()


def _parse_contact(header: str) -> dict[str, str]:
    lines = [line.strip() for line in header.splitlines() if line.strip()]
    email_match = re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", header)
    phone_match = re.search(r"(?:\+\d{1,3}\s*)?0?\d[\d ()-]{8,}\d", header)
    email = email_match.group(0) if email_match else ""
    phone = phone_match.group(0).strip() if phone_match else ""
    non_contact = [line for line in lines if line not in {email, phone}]
    return {
        "full_name": non_contact[0] if non_contact else "",
        "email": email,
        "phone": phone,
        "location": non_contact[1] if len(non_contact) > 1 else "",
        "linkedin": next((line for line in lines if "linkedin.com/" in line.lower()), ""),
        "title": "",
    }


def _parse_experience(section: str) -> list[dict[str, Any]]:
    """Parse common CV date/role/company layouts without inventing content."""
    lines = [line.strip() for line in section.splitlines() if line.strip()]
    starts = [(idx, match) for idx, line in enumerate(lines)
              if (match := _DATE_RANGE_RE.match(line))]
    experience: list[dict[str, Any]] = []
    for pos, (start, match) in enumerate(starts):
        end = starts[pos + 1][0] if pos + 1 < len(starts) else len(lines)
        body = lines[start + 1:end]
        company = body[0] if body else ""
        content = body[1:]
        achievements: list[dict[str, str]] = []
        current: list[str] = []
        for line in content:
            is_bullet = line.startswith(("•", "●", "▪", "◦"))
            if is_bullet and current:
                achievements.append({"text": _join_wrapped_lines(current)})
                current = []
            current.append(line.lstrip("•●▪◦ ").strip())
        if current:
            achievements.append({"text": _join_wrapped_lines(current)})
        experience.append({
            "role": match.group("role").strip(),
            "company": company,
            "period": match.group("period").strip(),
            "achievements": [item for item in achievements if item["text"]],
        })
    return experience


def _parse_skills_section(section: str) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    current_category = "Skills"
    current_text = ""
    for line in [line.strip() for line in section.splitlines() if line.strip()]:
        if ":" in line:
            if current_text:
                groups.append({
                    "category": current_category,
                    "items": [item.strip() for item in current_text.split(",") if item.strip()],
                })
            current_category, current_text = (part.strip() for part in line.split(":", 1))
        else:
            current_text = f"{current_text} {line}".strip()
    if current_text:
        groups.append({
            "category": current_category,
            "items": [item.strip() for item in current_text.split(",") if item.strip()],
        })
    return groups


def _parse_education(section: str) -> list[dict[str, str]]:
    lines = [line.strip() for line in section.splitlines() if line.strip()]
    education: list[dict[str, str]] = []
    idx = 0
    while idx < len(lines):
        match = re.match(r"^(?P<year>(?:19|20)\d{2}(?:\s*[–—-]\s*(?:19|20)\d{2})?)\s+(?P<qualification>.+)$", lines[idx])
        if not match:
            idx += 1
            continue
        education.append({
            "qualification": match.group("qualification").strip(),
            "institution": lines[idx + 1] if idx + 1 < len(lines) else "",
            "year": match.group("year").strip(),
        })
        idx += 2
    return education


def _count_experience_items(sections: dict[str, Any]) -> int:
    # Look in experience, profile (fallback if parser lumped experience there), or full text
    exp_text = (
        sections.get("experience")
        or sections.get("professional experience")
        or sections.get("work experience")
        or sections.get("employment")
        or sections.get("profile")  # pypdf sometimes lumps experience into profile
        or ""
    )
    if not exp_text:
        return 0
    # Count distinct year ranges (e.g. "2022 – Present", "07/2011 – 05/2022")
    dates = re.findall(r"\b(19|20)\d{2}\b", str(exp_text))
    # Divide by 2 (start/end per role) as a rough role count, minimum from unique years
    return max(len(set(dates)) - 1, len(dates) // 2)


# ── Schemas ───────────────────────────────────────────────────────────────────

class ResumeStatus(BaseModel):
    exists: bool
    filename: str | None = None
    uploaded_at: str | None = None
    parsed: bool = False
    sections: dict[str, bool] = {}
    skills_count: int = 0
    experience_count: int = 0
    proof_points_count: int = 0


class ParsePreviewResponse(BaseModel):
    """Returned by /upload — parsed CV preview for user review before confirming."""
    parsed_cv: dict[str, Any]
    warnings: list[str]
    filename: str
    raw_text_saved: bool


class ConfirmCVRequest(BaseModel):
    """Body for /confirm — the (possibly user-edited) parsed CV JSON."""
    parsed_cv: dict[str, Any]
    filename: str | None = None


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/status", response_model=ResumeStatus)
async def get_resume_status() -> ResumeStatus:
    """Return status of the currently stored master CV."""
    cv_path = _cv_path()
    meta_path = _meta_path()

    if not cv_path.exists():
        return ResumeStatus(exists=False)

    meta: dict[str, Any] = {}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text())
        except Exception:
            pass

    try:
        cv_data = json.loads(cv_path.read_text())
    except Exception:
        return ResumeStatus(exists=True, parsed=False, filename=meta.get("filename"))

    profile = load_profile()
    proof_count = len(profile.proof_points)

    sections_present: dict[str, bool] = {
        "personal": bool(cv_data.get("personal") or cv_data.get("contact") or cv_data.get("header")),
        "summary": bool(cv_data.get("summary") or cv_data.get("summary_variants") or cv_data.get("profile")),
        "experience": bool(cv_data.get("experience") or cv_data.get("employment") or cv_data.get("work_history")),
        "skills": bool(cv_data.get("skills")),
        "education": bool(cv_data.get("education")),
        "certifications": bool(cv_data.get("certifications")),
    }

    skills_count = 0
    skills = cv_data.get("skills", {})
    if isinstance(skills, dict):
        for v in skills.values():
            items = v.get("items", []) if isinstance(v, dict) else []
            skills_count += len(items)
    elif isinstance(skills, list):
        skills_count = len(skills)

    return ResumeStatus(
        exists=True,
        filename=meta.get("filename"),
        uploaded_at=meta.get("uploaded_at"),
        parsed=True,
        sections=sections_present,
        skills_count=skills_count,
        experience_count=meta.get("experience_count", 0),
        proof_points_count=proof_count,
    )


_MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB
# Next.js' rewrite proxy has a 30-second upstream timeout. Keep enough headroom
# for document extraction and response serialization; heuristic parsing remains
# available when the configured LLM is slow or unavailable.
_STRUCTURED_PARSE_TIMEOUT_SECONDS = 20


def _heuristic_cv(text: str) -> dict[str, Any]:
    """Return a grounded CV structure without requiring an LLM."""
    sections = _parse_sections(text)
    certifications = [
        line.lstrip("•●▪◦ ").strip()
        for line in str(sections.get("certifications", "")).splitlines()
        if line.lstrip("•●▪◦ ").strip()
    ]
    return {
        "personal": _parse_contact(str(sections.get("header", ""))),
        "summary_variants": {
            "default": sections.get("summary") or sections.get("profile") or ""
        },
        "experience": _parse_experience(str(sections.get("experience", ""))),
        "skills": _parse_skills_section(str(sections.get("skills", ""))),
        "certifications": certifications,
        "education": _parse_education(str(sections.get("education", ""))),
    }


def _is_complete_parse(parsed: dict[str, Any]) -> bool:
    """Require identity and career history before accepting a master CV parse."""
    personal = parsed.get("personal", {})
    return bool(
        isinstance(personal, dict)
        and personal.get("full_name")
        and parsed.get("experience")
    )


@router.post("/upload", response_model=ParsePreviewResponse)
async def upload_resume(file: UploadFile = File(...)) -> ParsePreviewResponse:
    """Upload a .docx or .pdf CV.

    Extracts text, runs structured LLM parsing with verbatim grounding checks,
    and returns the preview for user review. Does NOT persist the CV —
    call POST /resume/confirm to save it.
    """
    filename = file.filename or ""
    suffix = Path(filename).suffix.lower()
    if suffix not in (".docx", ".pdf"):
        raise HTTPException(status_code=422, detail="Only .docx and .pdf files are supported.")

    content = await file.read(_MAX_UPLOAD_BYTES + 1)
    if len(content) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large. Maximum upload size is 10 MB.")
    if not content:
        raise HTTPException(status_code=422, detail="Uploaded file is empty.")

    _data_dir().mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        if suffix == ".docx":
            text = _extract_text_from_docx(tmp_path)
        else:
            text = _extract_text_from_pdf(tmp_path)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to parse document: {exc}") from exc
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    # Persist raw text for semantic scoring (separate from structured CV)
    raw_text_saved = False
    try:
        from ..services.resume_store import save_resume_text  # noqa: PLC0415
        save_resume_text(text)
        raw_text_saved = True
    except Exception as _exc:
        import logging as _logging  # noqa: PLC0415
        _logging.getLogger(__name__).warning("Could not save resume text for scoring: %s", _exc)

    # Prefer the fast, grounded parser when it can identify the candidate and
    # employment history. This avoids making uploads depend on local-model speed.
    parsed_cv = _heuristic_cv(text)
    warnings: list[str] = []
    if not _is_complete_parse(parsed_cv):
        try:
            from ..services.llm_client import LLMClient  # noqa: PLC0415
            from ..services.cv_parser import parse_cv_text  # noqa: PLC0415
            parse_result = await asyncio.wait_for(
                parse_cv_text(text, LLMClient()),
                timeout=_STRUCTURED_PARSE_TIMEOUT_SECONDS,
            )
            if _is_complete_parse(parse_result.parsed):
                parsed_cv = parse_result.parsed
                warnings = parse_result.warnings
            else:
                warnings = ["Could not identify complete contact and employment history. Review the parsed CV before saving."]
        except TimeoutError:
            warnings = ["CV parsing timed out and the document structure could not be fully identified. Review before saving."]
        except Exception as exc:
            warnings = [f"CV parsing failed: {exc}. Review before saving."]

    return ParsePreviewResponse(
        parsed_cv=parsed_cv,
        warnings=warnings,
        filename=filename,
        raw_text_saved=raw_text_saved,
    )


@router.post("/confirm", response_model=ResumeStatus)
async def confirm_cv(body: ConfirmCVRequest) -> ResumeStatus:
    """Persist the (user-reviewed, possibly edited) parsed CV JSON.

    Validates the CV structure, writes to master_cv_path, invalidates the
    in-process cache so subsequent tailor calls see the new content immediately.
    """
    from ..services.master_cv_validator import validate_master_cv  # noqa: PLC0415

    cv_data = body.parsed_cv
    if not _is_complete_parse(cv_data):
        raise HTTPException(
            status_code=422,
            detail="Master CV must include the candidate name and at least one employment entry.",
        )
    validation_errors = validate_master_cv(cv_data)
    if validation_errors:
        # Advisory only — still save. Blocking errors are surfaced at tailor time.
        import logging as _logging  # noqa: PLC0415
        _logging.getLogger(__name__).warning("Master CV validation warnings: %s", validation_errors)

    _data_dir().mkdir(parents=True, exist_ok=True)
    cv_path = _cv_path()
    cv_path.write_text(json.dumps(cv_data, indent=2, ensure_ascii=False))
    invalidate_cache()

    filename = body.filename or "master_cv.json"
    exp_count = len(cv_data.get("experience", []))
    skills_flat: list[str] = []
    for grp in cv_data.get("skills", []):
        if isinstance(grp, dict):
            skills_flat.extend(grp.get("items", []))

    meta = {
        "filename": filename,
        "uploaded_at": datetime.utcnow().isoformat(),
        "experience_count": exp_count,
        "confirmed": True,
    }
    _meta_path().write_text(json.dumps(meta))

    sections_present: dict[str, bool] = {
        "personal": bool(cv_data.get("personal")),
        "summary": bool(cv_data.get("summary_variants")),
        "experience": bool(cv_data.get("experience")),
        "skills": bool(cv_data.get("skills")),
        "education": bool(cv_data.get("education")),
        "certifications": bool(cv_data.get("certifications")),
    }

    try:
        proof_count = len(load_profile().proof_points)
    except Exception:
        proof_count = 0

    return ResumeStatus(
        exists=True,
        filename=filename,
        uploaded_at=meta["uploaded_at"],
        parsed=True,
        sections=sections_present,
        skills_count=len(skills_flat),
        experience_count=exp_count,
        proof_points_count=proof_count,
    )


@router.get("/json")
async def get_resume_json() -> dict[str, Any]:
    """Return the raw parsed master CV JSON."""
    cv_path = _cv_path()
    if not cv_path.exists():
        raise HTTPException(status_code=404, detail="No master CV found. Upload one at /api/resume/upload.")
    try:
        return json.loads(cv_path.read_text())
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read CV: {exc}") from exc
