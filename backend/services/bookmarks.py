"""Bookmarks aggregation — the bookmarked subjects + topics in one read.

Topics come back with the breadcrumb (subject/chapter/document) the client
needs to deep-link into the study view, mirroring the search service's shape.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.models import Chapter, Document, Subject, Topic
from backend.models.enums import TopicPriority, TopicStatus


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
    subjects: list[Subject]
    topics: list[BookmarkTopic]


def list_bookmarks(session: Session) -> Bookmarks:
    """All bookmarked subjects (name-sorted) and topics (title-sorted)."""
    subjects = list(
        session.execute(
            select(Subject)
            .where(Subject.bookmarked.is_(True))
            .order_by(func.lower(Subject.name), Subject.id)
        ).scalars()
    )

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
