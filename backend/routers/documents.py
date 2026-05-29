"""Documents router — upload/ingest and structure detection (Phase 6)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from backend.db.database import get_session
from backend.schemas.structure import (
    ConfirmStructureIn,
    ConfirmStructureResult,
    DocumentOut,
    ProposedStructureOut,
    UploadResult,
)
from backend.services import documents as docsvc

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("", response_model=UploadResult, status_code=201)
async def upload_document(
    subject_id: int = Form(...),
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
) -> UploadResult:
    """Ingest an uploaded PDF and create its Document (structure not yet built)."""
    data = await file.read()
    try:
        document, result = docsvc.create_document(
            session,
            subject_id=subject_id,
            filename=file.filename or "upload.pdf",
            data=data,
        )
    except docsvc.InvalidPDFError:
        raise HTTPException(status_code=400, detail="Uploaded file is not a PDF")
    except docsvc.SubjectNotFoundError:
        raise HTTPException(status_code=404, detail="Subject not found")

    return UploadResult(
        document=DocumentOut.model_validate(document),
        page_count=result.page_count,
        is_scanned=result.is_scanned,
    )


@router.get("/{document_id}/structure", response_model=ProposedStructureOut)
def document_structure(
    document_id: int,
    session: Session = Depends(get_session),
) -> ProposedStructureOut:
    """Propose a chapter/topic tree from the document's ingested markdown."""
    try:
        structure = docsvc.detect_for_document(session, document_id)
    except docsvc.DocumentNotFoundError:
        raise HTTPException(status_code=404, detail="Document not found")
    except docsvc.MarkdownUnavailableError:
        raise HTTPException(
            status_code=409, detail="Document markdown unavailable; re-ingest needed"
        )
    return ProposedStructureOut.model_validate(structure)


@router.post(
    "/{document_id}/structure",
    response_model=ConfirmStructureResult,
    status_code=201,
)
def confirm_structure(
    document_id: int,
    payload: ConfirmStructureIn,
    session: Session = Depends(get_session),
) -> ConfirmStructureResult:
    """Persist the reviewed chapter/topic tree and enqueue its non-skip topics."""
    try:
        counts = docsvc.confirm_structure(
            session,
            document_id,
            chapters=payload.chapters,
            exam_date=payload.exam_date,
        )
    except docsvc.DocumentNotFoundError:
        raise HTTPException(status_code=404, detail="Document not found")
    except docsvc.AlreadyConfirmedError:
        raise HTTPException(
            status_code=409, detail="Document structure already confirmed"
        )

    return ConfirmStructureResult(
        document_id=document_id,
        chapters_created=counts.chapters_created,
        topics_created=counts.topics_created,
        topics_enqueued=counts.topics_enqueued,
    )
