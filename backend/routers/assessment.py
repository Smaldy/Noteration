"""Assessment router — aggregated quiz + flashcard decks (chapter/document/subject)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.db.database import get_session
from backend.models.enums import DocumentMode
from backend.schemas.assessment import AggregateAssessmentOut
from backend.services import assessment as asmt

router = APIRouter(prefix="/assessment", tags=["assessment"])


@router.get("/topics", response_model=AggregateAssessmentOut)
def topics_assessment(
    topic_id: list[int] = Query(default=[]),
    session: Session = Depends(get_session),
) -> asmt.AggregateAssessment:
    """Combined quiz + flashcards across an explicit set of topics.

    Powers the custom topic selector: ``?topic_id=1&topic_id=2&...``. Requires at
    least one topic id (422 otherwise). Unknown ids are simply absent from the
    pool. Declared before the ``/{scope}/{id}`` routes so ``topics`` stays literal.
    """
    if not topic_id:
        raise HTTPException(status_code=422, detail="Select at least one topic")
    return asmt.topics_assessment(session, topic_id)


@router.get("/chapters/{chapter_id}", response_model=AggregateAssessmentOut)
def chapter_assessment(
    chapter_id: int,
    session: Session = Depends(get_session),
) -> asmt.AggregateAssessment:
    """Combined quiz + flashcards across all topics in a chapter (argument)."""
    try:
        return asmt.chapter_assessment(session, chapter_id)
    except asmt.ChapterNotFoundError:
        raise HTTPException(status_code=404, detail="Chapter not found")


@router.get("/documents/{document_id}", response_model=AggregateAssessmentOut)
def document_assessment(
    document_id: int,
    session: Session = Depends(get_session),
) -> asmt.AggregateAssessment:
    """Combined quiz + flashcards across a whole document (all its chapters)."""
    try:
        return asmt.document_assessment(session, document_id)
    except asmt.DocumentNotFoundError:
        raise HTTPException(status_code=404, detail="Document not found")


@router.get("/subjects/{subject_id}", response_model=AggregateAssessmentOut)
def subject_assessment(
    subject_id: int,
    mode: DocumentMode | None = None,
    session: Session = Depends(get_session),
) -> asmt.AggregateAssessment:
    """Combined quiz + flashcards across a whole subject.

    ``?mode=exam`` scopes to the subject's exam documents (Exam Prep), so study
    material isn't mixed in.
    """
    try:
        return asmt.subject_assessment(session, subject_id, mode=mode)
    except asmt.SubjectNotFoundError:
        raise HTTPException(status_code=404, detail="Subject not found")
