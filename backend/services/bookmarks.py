"""Bookmarks aggregation — the bookmarked subjects + topics in one read.

Topics come back with the breadcrumb (subject/chapter/document) the client
needs to deep-link into the study view, mirroring the search service's shape.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.models import Chapter, Document, Subject, Topic
from backend.models.enums import TopicPriority, TopicStatus


@dataclass
class BookmarkSubject:
    id: int
    name: str
    accent_color: str | None
    exam_date: date | None
    bookmarked: bool
    created_at: datetime
    # Primary document to deep-link into the subject's notes; ``None`` when the
    # subject has no documents yet (so the chip stays non-navigable).
    document_id: int | None


@dataclass
class BookmarkTopic:
    id: int
    title: str
    subject_id: int
    subject_name: str
    document_id: int
    chapter_title: str
    status: TopicStatus
    priority: TopicPriority


@dataclass
class Bookmarks:
    subjects: list[BookmarkSubject]
    topics: list[BookmarkTopic]


def list_bookmarks(session: Session) -> Bookmarks:
    """All bookmarked subjects (name-sorted) and topics (title-sorted)."""
    subject_rows = list(
        session.execute(
            select(Subject)
            .where(Subject.bookmarked.is_(True))
            .order_by(func.lower(Subject.name), Subject.id)
        ).scalars()
    )

    # Map each bookmarked subject to its primary document so the Bookmarks view
    # can deep-link into the notes. Ordered (order_index, id) to match the
    # Library, so a click opens the same first document the user sees there.
    doc_by_subject: dict[int, int] = {}
    if subject_rows:
        for sid, did in session.execute(
            select(Document.subject_id, Document.id)
            .where(Document.subject_id.in_([s.id for s in subject_rows]))
            .order_by(Document.order_index, Document.id)
        ).all():
            doc_by_subject.setdefault(sid, did)

    subjects = [
        BookmarkSubject(
            id=s.id,
            name=s.name,
            accent_color=s.accent_color,
            exam_date=s.exam_date,
            bookmarked=s.bookmarked,
            created_at=s.created_at,
            document_id=doc_by_subject.get(s.id),
        )
        for s in subject_rows
    ]

    topic_rows = session.execute(
        select(Topic, Chapter, Document, Subject)
        .join(Chapter, Topic.chapter_id == Chapter.id)
        .join(Document, Chapter.document_id == Document.id)
        .join(Subject, Document.subject_id == Subject.id)
        .where(Topic.bookmarked.is_(True))
        .order_by(func.lower(Topic.title), Topic.id)
    ).all()
    topics = [
        BookmarkTopic(
            id=topic.id,
            title=topic.title,
            subject_id=subject.id,
            subject_name=subject.name,
            document_id=document.id,
            chapter_title=chapter.title,
            status=topic.status,
            priority=topic.priority,
        )
        for topic, chapter, document, subject in topic_rows
    ]
    return Bookmarks(subjects=subjects, topics=topics)
