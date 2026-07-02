"""Search service — find topics (and chapters) by title across the library.

Substring, case-insensitive match on titles, optionally scoped to one subject.
Topics are the atomic studyable unit so they rank first; chapters fill any
remaining budget. Kept dependency-free and synchronous like the other services.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import Chapter, Document, Subject, Topic
from backend.models.enums import TopicPriority, TopicStatus


@dataclass
class SearchHit:
    """One match, flattened with the breadcrumb needed to navigate to it."""

    kind: str  # "topic" | "chapter"
    id: int  # topic_id or chapter_id
    title: str
    subject_id: int
    subject_name: str
    document_id: int
    document_filename: str
    chapter_title: str
    status: TopicStatus | None = None  # topics only
    priority: TopicPriority | None = None  # topics only


def _escape_like(term: str) -> str:
    """Escape LIKE wildcards so a literal % or _ in the query isn't a wildcard."""
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def search(
    session: Session,
    *,
    query: str,
    subject_id: int | None = None,
    limit: int = 30,
) -> list[SearchHit]:
    """Title search over topics then chapters, newest-relevance by title order.

    Returns at most ``limit`` hits total. ``subject_id`` (when given) scopes both
    to that subject via the denormalized ``Chapter.subject_id``. An empty
    ``query`` with a ``subject_id`` lists every topic/chapter in that subject
    (a subject-only filter, no title needed); an empty query with no
    ``subject_id`` has nothing to scope by, so it returns no hits.
    """
    q = query.strip()
    if not q and subject_id is None:
        return []
    pattern = f"%{_escape_like(q)}%" if q else None

    topic_stmt = (
        select(Topic, Chapter, Document, Subject)
        .join(Chapter, Topic.chapter_id == Chapter.id)
        .join(Document, Chapter.document_id == Document.id)
        .join(Subject, Document.subject_id == Subject.id)
    )
    if pattern is not None:
        topic_stmt = topic_stmt.where(Topic.title.ilike(pattern, escape="\\"))
    if subject_id is not None:
        topic_stmt = topic_stmt.where(Chapter.subject_id == subject_id)
    topic_stmt = topic_stmt.order_by(Topic.title, Topic.id).limit(limit)

    hits: list[SearchHit] = [
        SearchHit(
            kind="topic",
            id=topic.id,
            title=topic.title,
            subject_id=subject.id,
            subject_name=subject.name,
            document_id=document.id,
            document_filename=document.filename,
            chapter_title=chapter.title,
            status=topic.status,
            priority=topic.priority,
        )
        for topic, chapter, document, subject in session.execute(topic_stmt).all()
    ]

    remaining = limit - len(hits)
    if remaining <= 0:
        return hits

    chapter_stmt = (
        select(Chapter, Document, Subject)
        .join(Document, Chapter.document_id == Document.id)
        .join(Subject, Document.subject_id == Subject.id)
    )
    if pattern is not None:
        chapter_stmt = chapter_stmt.where(Chapter.title.ilike(pattern, escape="\\"))
    if subject_id is not None:
        chapter_stmt = chapter_stmt.where(Chapter.subject_id == subject_id)
    chapter_stmt = chapter_stmt.order_by(Chapter.title, Chapter.id).limit(remaining)

    hits.extend(
        SearchHit(
            kind="chapter",
            id=chapter.id,
            title=chapter.title,
            subject_id=subject.id,
            subject_name=subject.name,
            document_id=document.id,
            document_filename=document.filename,
            chapter_title=chapter.title,
        )
        for chapter, document, subject in session.execute(chapter_stmt).all()
    )
    return hits
