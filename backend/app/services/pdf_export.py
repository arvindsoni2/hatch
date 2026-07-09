"""Capability-gated PDF export service for generated DOCX packages."""
from __future__ import annotations

import asyncio
import shutil
import subprocess
from pathlib import Path
from typing import TypeAlias

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.application import Application
from ..models.document import GeneratedDocument
from ..models.document_asset import GeneratedDocumentAsset

PDF_UNAVAILABLE_MESSAGE = "PDF export is not installed in this setup."
PdfConverter: TypeAlias = tuple[str, ...]


class PdfExportUnavailableError(RuntimeError):
    """Raised when this install has no allowlisted local PDF converter."""


class PdfExportFailedError(RuntimeError):
    """Raised when an available converter fails to produce a PDF."""


def find_pdf_converter() -> PdfConverter | None:
    """Return an allowlisted local converter command, if already installed."""
    for binary in ("libreoffice", "soffice"):
        resolved = shutil.which(binary)
        if resolved:
            return (resolved,)
    return None


def pdf_export_capability() -> dict[str, str | bool]:
    converter = find_pdf_converter()
    return {
        "available": converter is not None,
        "status": "available" if converter else "unavailable",
        "message": None if converter else PDF_UNAVAILABLE_MESSAGE,
    }


async def convert_docx_to_pdf(source_path: Path, output_path: Path, converter: PdfConverter) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        *converter,
        "--headless",
        "--convert-to",
        "pdf",
        "--outdir",
        str(output_path.parent),
        str(source_path),
    ]
    completed = await asyncio.to_thread(
        subprocess.run,
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    produced_path = output_path.parent / f"{source_path.stem}.pdf"
    if completed.returncode != 0 or not produced_path.exists():
        error = (completed.stderr or completed.stdout or "PDF converter did not produce a file.").strip()
        raise PdfExportFailedError(error)
    if produced_path != output_path:
        produced_path.replace(output_path)
    return output_path


async def export_package_pdf(
    db: AsyncSession,
    package_id: str,
    *,
    kind: str = "cv",
) -> GeneratedDocumentAsset:
    if kind not in {"cv", "cover_letter"}:
        raise ValueError("kind must be cv or cover_letter")

    converter = find_pdf_converter()
    if converter is None:
        raise PdfExportUnavailableError(PDF_UNAVAILABLE_MESSAGE)

    application = await db.get(Application, package_id)
    if application is None or not application.is_active:
        raise LookupError("Application package not found.")

    result = await db.execute(
        select(GeneratedDocument)
        .where(
            GeneratedDocument.application_id == package_id,
            GeneratedDocument.document_type == kind,
            GeneratedDocument.file_path.isnot(None),
        )
        .order_by(desc(GeneratedDocument.created_at), desc(GeneratedDocument.version))
    )
    document = result.scalars().first()
    if document is None or document.file_path is None:
        raise LookupError("Generated document not found.")

    source_path = Path(document.file_path)
    if not source_path.exists():
        raise LookupError("Generated document file is missing.")

    output_path = source_path.with_suffix(".pdf")
    await convert_docx_to_pdf(source_path, output_path, converter)

    asset = GeneratedDocumentAsset(
        application_id=package_id,
        package_id=package_id,
        source_document_id=document.id,
        kind=kind,
        format="pdf",
        path_or_blob_ref=str(output_path),
        generation_status="completed",
    )
    db.add(asset)
    await db.flush()
    await db.refresh(asset)
    return asset


async def get_document_asset(db: AsyncSession, asset_id: str) -> GeneratedDocumentAsset | None:
    return await db.get(GeneratedDocumentAsset, asset_id)
