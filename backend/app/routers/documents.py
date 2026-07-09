"""Document asset export and download endpoints."""
from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..schemas.document_asset import GeneratedDocumentAssetRead
from ..services.pdf_export import (
    PDF_UNAVAILABLE_MESSAGE,
    PdfExportFailedError,
    PdfExportUnavailableError,
    export_package_pdf,
    get_document_asset,
)

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.post("/{package_id}/export/pdf", response_model=GeneratedDocumentAssetRead, status_code=201)
async def export_pdf(
    package_id: str,
    kind: Literal["cv", "cover_letter"] = Query("cv"),
    db: AsyncSession = Depends(get_db),
) -> GeneratedDocumentAssetRead:
    try:
        asset = await export_package_pdf(db, package_id, kind=kind)
    except PdfExportUnavailableError as exc:
        raise HTTPException(status_code=503, detail=PDF_UNAVAILABLE_MESSAGE) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except PdfExportFailedError as exc:
        raise HTTPException(status_code=500, detail=f"PDF export failed: {exc}") from exc
    return GeneratedDocumentAssetRead.model_validate(asset)


@router.get("/assets/{asset_id}")
async def download_asset(asset_id: str, db: AsyncSession = Depends(get_db)) -> FileResponse:
    asset = await get_document_asset(db, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Document asset not found.")
    path = Path(asset.path_or_blob_ref)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Document asset file is missing.")
    filename = f"{asset.kind}-{asset.id}.{asset.format}"
    return FileResponse(path, media_type="application/pdf", filename=filename)
