"""Aggregated assessment — pool a topic's MCQs + flashcards up the hierarchy.

Per-topic quiz/flashcards already exist (the study tabs). This service rolls them
up so a student can practise a whole **argument** (chapter), a whole **deck**
(document), or a whole **subject** at once. Flashcards keep their ids, so SM-2
review still posts per-card; the quiz is client-side. Read-only and N+1-free.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.models import MCQ, Chapter, Document, Flashcard, Subject, Topic
from backend.models.enums import DocumentMode


class ChapterNotFoundError(LookupError):
    """Referenced chapter does not exist."""


class DocumentNotFoundError(LookupError):
    """Referenced document does not exist."""


class SubjectNotFoundError(LookupError):
    """Referenced subject does not exist."""


@dataclass
class AggregateAssessment:
    """A pooled quiz + flashcard deck for one scope (chapter/document/subject)."""

    scope: str  # "chapter" | "document" | "subject"
    id: int
    title: str
    topic_count: int
    mcqs: list[MCQ]
    flashcards: list[Flashcard]


# Stable reading order so pooled questions/cards group by chapter then topic.
_ORDER = (Chapter.order_index, Chapter.id, Topic.order_index, Topic.id)


def _pool(
    session: Session, conditions: list, *, with_document: bool = False
) -> tuple[list[MCQ], list[Flashcard], int]:
    """Return (mcqs, cards, topic_count) for topics matching ``conditions``.

    All three queries join Topic→Chapter (and optionally →Document, when a
    document-level filter like ``mode`` is in play), so the conditions can target
    any level uniformly.
    """
    mcq_q = (
        select(MCQ)
        .join(Topic, MCQ.topic_id == Topic.id)
        .join(Chapter, Topic.chapter_id == Chapter.id)
    )
    card_q = (
        select(Flashcard)
        .join(Topic, Flashcard.topic_id == Topic.id)
        .join(Chapter, Topic.chapter_id == Chapter.id)
    )
    topic_q = (
        select(func.count(Topic.id))
        .select_from(Topic)
        .join(Chapter, Topic.chapter_id == Chapter.id)
    )
    if with_document:
        mcq_q = mcq_q.join(Document, Chapter.document_id == Document.id)
        card_q = card_q.join(Document, Chapter.document_id == Document.id)
        topic_q = topic_q.join(Document, Chapter.document_id == Document.id)

    mcqs = list(session.scalars(mcq_q.where(*conditions).order_by(*_ORDER, MCQ.id)))
    cards = list(
        session.scalars(card_q.where(*conditions).order_by(*_ORDER, Flashcard.id))
    )
    topic_count = session.scalar(topic_q.where(*conditions)) or 0
    return mcqs, cards, topic_count


def topics_assessment(
    session: Session, topic_ids: list[int]
) -> AggregateAssessment:
    """Pool the quiz + flashcards across an explicit set of topics.

    Powers the custom topic selector (pick any subset, or "select all"). The title
    is the common subject's name when every chosen topic shares one subject, else
    empty (the UI shows a generic "Selected topics" label). ``id`` is 0 — a custom
    set has no single owning row. Order matches the other scopes (chapter→topic).
    """
    if not topic_ids:
        return AggregateAssessment("topics", 0, "", 0, [], [])
    mcqs, cards, count = _pool(session, [Topic.id.in_(topic_ids)])
    subject_ids = set(
        session.scalars(
            select(Chapter.subject_id)
            .join(Topic, Topic.chapter_id == Chapter.id)
            .where(Topic.id.in_(topic_ids))
            .distinct()
        )
    )
    title = ""
    if len(subject_ids) == 1:
        subject = session.get(Subject, next(iter(subject_ids)))
        title = subject.name if subject is not None else ""
    return AggregateAssessment("topics", 0, title, count, mcqs, cards)


def chapter_assessment(session: Session, chapter_id: int) -> AggregateAssessment:
    """Pool the quiz + flashcards across all topics in one chapter (argument)."""
    chapter = session.get(Chapter, chapter_id)
    if chapter is None:
        raise ChapterNotFoundError(chapter_id)
    mcqs, cards, count = _pool(session, [Chapter.id == chapter_id])
    return AggregateAssessment("chapter", chapter_id, chapter.title, count, mcqs, cards)


def document_assessment(session: Session, document_id: int) -> AggregateAssessment:
    """Pool the quiz + flashcards across a whole document (all its chapters)."""
    document = session.get(Document, document_id)
    if document is None:
        raise DocumentNotFoundError(document_id)
    mcqs, cards, count = _pool(session, [Chapter.document_id == document_id])
    return AggregateAssessment(
        "document", document_id, document.filename, count, mcqs, cards
    )


def subject_assessment(
    session: Session, subject_id: int, *, mode: DocumentMode | None = None
) -> AggregateAssessment:
    """Pool the quiz + flashcards across a whole subject (all its arguments).

    Uses the denormalized ``Chapter.subject_id``. ``mode`` scopes to one section's
    documents (e.g. ``exam`` for Exam Prep, so study docs aren't mixed in).
    """
    subject = session.get(Subject, subject_id)
    if subject is None:
        raise SubjectNotFoundError(subject_id)
    conditions: list = [Chapter.subject_id == subject_id]
    with_document = False
    if mode is not None:
        conditions.append(Document.mode == mode)
        with_document = True
    mcqs, cards, count = _pool(session, conditions, with_document=with_document)
    return AggregateAssessment("subject", subject_id, subject.name, count, mcqs, cards)
