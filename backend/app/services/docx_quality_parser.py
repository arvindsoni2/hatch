"""Moderate DOCX text/section parser for quality checks."""
from __future__ import annotations
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree


def parse_docx_quality(path: str) -> dict:
    try:
        with zipfile.ZipFile(Path(path)) as archive:
            root = ElementTree.fromstring(archive.read("word/document.xml"))
        text = "\n".join(node.text or "" for node in root.iter() if node.tag.endswith("}t"))
    except Exception:
        text = ""
    lowered = text.lower()
    sections = {
        "summary": any(x in lowered for x in ("professional summary", "profile")),
        "skills": "skills" in lowered,
        "experience": "experience" in lowered,
        "education": "education" in lowered,
        "certifications": "certification" in lowered,
    }
    return {
        "text": text, "text_extraction_chars": len(text),
        "core_sections": sections,
        "contact_detection": {
            "name": bool(text.strip().splitlines()),
            "email": bool(re.search(r"[^@\s]+@[^@\s]+\.[^@\s]+", text)),
            "phone": bool(re.search(r"\+?[\d ()-]{8,}", text)),
            "location": False,
        },
        "heading_detection": "good" if sum(sections.values()) >= 3 else "advisory",
        "bullet_detection": "good" if "•" in text or len(text.splitlines()) > 8 else "advisory",
    }
