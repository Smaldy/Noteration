"""Documents router — upload/ingest and structure detection (Phase 6)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from sqlalchemy.orm import Session

from backend.db.database import get_session
from backend.models.enums import DocumentMode
from backend.schemas.library import DocumentSummaryOut
from backend.schemas.reorder import ReorderRequest
from backend.schemas.structure import (
    ConfirmStructureIn,
    ConfirmStructureResult,
    DocumentOut,
    ProposedStructureOut,
    UploadResult,
)
from backend.schemas.topic import DocumentTreeOut
from backend.services import documents as docsvc

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("", response_model=list[DocumentSummaryOut])
def list_documents(
    mode: DocumentMode | None = None,
    session: Session = Depends(get_session),
) -> list[docsvc.DocumentSummary]:
    """Document list with subject info and topic-ready progress.

    ``?mode=study`` scopes to the Library, ``?mode=exam`` to the Exam Prep
    section; omitting it returns every document.
    """
    return docsvc.list_documents(session, mode=mode)


@router.put("/reorder", status_code=204)
def reorder_documents(
    payload: ReorderRequest,
    session: Session = Depends(get_session),
) -> Response:
    """Persist the manual Library order (drag-and-drop)."""
    docsvc.reorder_documents(session, payload.ids)
    return Response(status_code=204)


@router.post("", response_model=UploadResult, status_code=201)
async def upload_document(
    subject_id: int = Form(...),
    file: UploadFile = File(...),
    mode: DocumentMode = Form(DocumentMode.study),
    session: Session = Depends(get_session),
) -> UploadResult:
    """Ingest an uploaded PDF and create its Document (structure not yet built).

    ``mode`` (form field) selects the section: ``study`` (Library, default) or
    ``exam`` (Exam Prep — assessment-only).
    """
    data = await file.read()
    try:
        document, result = docsvc.create_document(
            session,
            subject_id=subject_id,
            filename=file.filename or "upload.pdf",
            data=data,
            mode=mode,
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


@router.get("/{document_id}/tree", response_model=DocumentTreeOut)
def document_tree(
    document_id: int,
    session: Session = Depends(get_session),
) -> docsvc.DocumentTree:
    """The confirmed chapter/topic tree (Study View sidebar)."""
    try:
        return docsvc.get_document_tree(session, document_id)
    except docsvc.DocumentNotFoundError:
        raise HTTPException(status_code=404, detail="Document not found")


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
