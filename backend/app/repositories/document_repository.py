"""Database access layer for GeneratedDocument records."""
from __future__ import annotations

import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.document import GeneratedDocument
from ..schemas.document import DocumentListItem, GeneratedDocumentRead

logger = logging.getLogger(__name__)


class DocumentRepository:
    """All database operations for generated CV and cover letter documents."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        application_id: str,
        document_type: str,
        version: int,
        file_path: str,
        file_size_bytes: int,
        jd_analysis_snapshot: str | None = None,
        tailoring_params: str | None = None,
        ats_score: int | None = None,
        ats_details: str | None = None,
        variant_label: str | None = None,
        status: str = "generated",
    ) -> GeneratedDocumentRead:
        """Insert a new document record.

        Returns:
            GeneratedDocumentRead schema.
        """
        doc = GeneratedDocument(
            application_id=application_id,
            document_type=document_type,
            version=version,
            file_path=file_path,
            file_size_bytes=file_size_bytes,
            jd_analysis_snapshot=jd_analysis_snapshot,
            tailoring_params=tailoring_params,
            ats_score=ats_score,
            ats_details=ats_details,
            variant_label=variant_label,
            status=status,
        )
        self._session.add(doc)
        await self._session.flush()
        await self._session.refresh(doc)
        return GeneratedDocumentRead.model_validate(doc)

    async def get_by_id(self, doc_id: str) -> GeneratedDocumentRead | None:
        """Fetch a document by primary key.

        Args:
            doc_id: UUID string.

        Returns:
            GeneratedDocumentRead or None.
        """
        result = await self._session.execute(
            select(GeneratedDocument).where(GeneratedDocument.id == doc_id)
        )
        doc = result.scalar_one_or_none()
        return GeneratedDocumentRead.model_validate(doc) if doc else None

    async def list_by_application(
        self,
        application_id: str,
        doc_type: str | None = None,
    ) -> list[DocumentListItem]:
        """List documents for an application, optionally filtered by type.

        Args:
            application_id: UUID of the application.
            doc_type: "cv" or "cover_letter" filter, or None for all.

        Returns:
            List of DocumentListItem sorted newest first.
        """
        stmt = select(GeneratedDocument).where(
            GeneratedDocument.application_id == application_id
        )
        if doc_type:
            stmt = stmt.where(GeneratedDocument.document_type == doc_type)
        stmt = stmt.order_by(GeneratedDocument.created_at.desc())

        result = await self._session.execute(stmt)
        docs = result.scalars().all()
        return [DocumentListItem.model_validate(d) for d in docs]

    async def get_latest_version(self, application_id: str, doc_type: str) -> int:
        """Return the highest version number for this application+type combination.

        Args:
            application_id: UUID of the application.
            doc_type: "cv" or "cover_letter".

        Returns:
            Current max version (0 if no documents exist).
        """
        result = await self._session.execute(
            select(func.max(GeneratedDocument.version)).where(
                GeneratedDocument.application_id == application_id,
                GeneratedDocument.document_type == doc_type,
            )
        )
        max_ver = result.scalar_one_or_none()
        return max_ver or 0

    async def update_status(self, doc_id: str, status: str) -> None:
        """Update the status field of a document.

        Args:
            doc_id: UUID of the document.
            status: New status string.
        """
        result = await self._session.execute(
            select(GeneratedDocument).where(GeneratedDocument.id == doc_id)
        )
        doc = result.scalar_one_or_none()
        if doc:
            doc.status = status
            await self._session.flush()

    async def update_ats_score(self, doc_id: str, score: int, details: str) -> None:
        """Update the ATS score and details for a document.

        Args:
            doc_id: UUID of the document.
            score: Integer ATS score (0–100).
            details: JSON string of ATSScoreResult.
        """
        result = await self._session.execute(
            select(GeneratedDocument).where(GeneratedDocument.id == doc_id)
        )
        doc = result.scalar_one_or_none()
        if doc:
            doc.ats_score = score
            doc.ats_details = details
            await self._session.flush()
