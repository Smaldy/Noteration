"""Subject service — list + create.

Thin by design: a subject is just a name (+ optional accent color and exam
date) at the top of the hierarchy. The upload UI lists subjects to pick from
and creates one inline when needed. The service owns its transaction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.models import Chapter, Document, Flashcard, MCQ, Subject, Topic
from backend.models.enums import DocumentMode
from backend.services.pipeline.pdf_outline import is_trash


def list_subjects(session: Session) -> list[Subject]:
    """All subjects, name-sorted (case-insensitive) for the picker."""
    return list(
        session.execute(
            select(Subject).order_by(func.lower(Subject.name), Subject.id)
        ).scalars()
    )


def create_subject(
    session: Session,
    *,
    name: str,
    accent_color: str | None = None,
    exam_date: date | None = None,
) -> Subject:
    """Create and persist a subject. Name is trimmed; no uniqueness enforced."""
    subject = Subject(
        name=name.strip(),
        accent_color=accent_color,
        exam_date=exam_date,
    )
    session.add(subject)
    session.commit()
    session.refresh(subject)
    return subject


class SubjectNotFoundError(LookupError):
    """Referenced subject does not exist."""


# --- subject-wide topic tree (for the custom practice selector) -------------


@dataclass
class SelectableTopic:
    id: int
    title: str
    mcq_count: int
    flashcard_count: int


@dataclass
class SelectableChapter:
    id: int
    title: str
    topics: list[SelectableTopic] = field(default_factory=list)


@dataclass
class SelectableDocument:
    id: int
    filename: str
    mode: DocumentMode
    chapters: list[SelectableChapter] = field(default_factory=list)


@dataclass
class SubjectTopicTree:
    subject_id: int
    subject_name: str
    documents: list[SelectableDocument] = field(default_factory=list)


def get_subject_topic_tree(
    session: Session, subject_id: int, *, mode: DocumentMode | None = None
) -> SubjectTopicTree:
    """Every topic in a subject, grouped document→chapter, with per-topic counts.

    Powers the custom topic selector: the user ticks topics across the subject's
    PDFs (optionally scoped to one ``mode`` — study vs exam — so the Study and
    Exam-Prep selectors stay coherent) and pools their quiz/flashcards. Each topic
    carries its MCQ and flashcard counts so the UI can show "12 cards / 3 q" and
    grey out topics with nothing generated yet. Front/back-matter is filtered the
    same way as the study sidebar (``is_trash``). N+1-free: one query per level
    plus two grouped count queries.
    """
    subject = session.get(Subject, subject_id)
    if subject is None:
        raise SubjectNotFoundError(subject_id)

    doc_q = select(Document).where(Document.subject_id == subject_id)
    if mode is not None:
        doc_q = doc_q.where(Document.mode == mode)
    documents = list(
        session.scalars(doc_q.order_by(Document.order_index, Document.id))
    )
    if not documents:
        return SubjectTopicTree(subject_id, subject.name, [])
    doc_ids = [d.id for d in documents]

    chapters = list(
        session.scalars(
            select(Chapter)
            .where(Chapter.document_id.in_(doc_ids))
            .order_by(Chapter.order_index, Chapter.id)
        )
    )
    topics = list(
        session.scalars(
            select(Topic)
            .join(Chapter, Topic.chapter_id == Chapter.id)
            .where(Chapter.document_id.in_(doc_ids))
            .order_by(Topic.order_index, Topic.id)
        )
    )

    # Per-topic assessment counts in two grouped queries (no N+1).
    mcq_counts = dict(
        session.execute(
            select(MCQ.topic_id, func.count(MCQ.id))
            .join(Topic, MCQ.topic_id == Topic.id)
            .join(Chapter, Topic.chapter_id == Chapter.id)
            .where(Chapter.document_id.in_(doc_ids))
            .group_by(MCQ.topic_id)
        ).all()
    )
    card_counts = dict(
        session.execute(
            select(Flashcard.topic_id, func.count(Flashcard.id))
            .join(Topic, Flashcard.topic_id == Topic.id)
            .join(Chapter, Topic.chapter_id == Chapter.id)
            .where(Chapter.document_id.in_(doc_ids))
            .group_by(Flashcard.topic_id)
        ).all()
    )

    topics_by_chapter: dict[int, list[SelectableTopic]] = {}
    for topic in topics:
        if is_trash(topic.title):
            continue
        topics_by_chapter.setdefault(topic.chapter_id, []).append(
            SelectableTopic(
                id=topic.id,
                title=topic.title,
                mcq_count=mcq_counts.get(topic.id, 0),
                flashcard_count=card_counts.get(topic.id, 0),
            )
        )

    chapters_by_doc: dict[int, list[SelectableChapter]] = {}
    for chapter in chapters:
        if is_trash(chapter.title):
            continue
        chapter_topics = topics_by_chapter.get(chapter.id, [])
        if not chapter_topics:
            continue  # nothing selectable here
        chapters_by_doc.setdefault(chapter.document_id, []).append(
            SelectableChapter(id=chapter.id, title=chapter.title, topics=chapter_topics)
        )

    doc_nodes = [
        SelectableDocument(
            id=document.id,
            filename=document.filename,
            mode=document.mode,
            chapters=chapters_by_doc.get(document.id, []),
        )
        for document in documents
        if chapters_by_doc.get(document.id)
    ]
    return SubjectTopicTree(subject_id, subject.name, doc_nodes)


def set_bookmark(session: Session, subject_id: int, *, bookmarked: bool) -> Subject:
    """Set a subject's bookmark flag. Raises ``SubjectNotFoundError`` if missing."""
    subject = session.get(Subject, subject_id)
    if subject is None:
        raise SubjectNotFoundError(subject_id)
    subject.bookmarked = bookmarked
    session.commit()
    session.refresh(subject)
    return subject


def delete_subject(session: Session, subject_id: int) -> None:
    """Delete a subject and its whole hierarchy.

    Cascades down documents → chapters → topics and everything generated from
    those topics. Raises ``SubjectNotFoundError`` if it does not exist.
    """
    subject = session.get(Subject, subject_id)
    if subject is None:
        raise SubjectNotFoundError(subject_id)
    session.delete(subject)
    session.commit()
