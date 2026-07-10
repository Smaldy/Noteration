"""To-do list service — the floating widget's pinned-topic list.

Items are bare topic references (one per topic); the checked state is the
topic's ``studied`` flag, owned by ``topics.set_studied``. Reads join up the
hierarchy so the widget can label items and deep-link into the Study View.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.models import Chapter, Document, Subject, TodoItem, Topic


@dataclass
class TodoItemView:
    """One to-do row, flattened for the widget (labels + deep-link ids)."""

    topic_id: int
    title: str
    chapter_title: str
    document_id: int
    document_filename: str
    subject_id: int
    subject_name: str
    studied: bool
    created_at: datetime


def _item_rows(db: Session) -> list[TodoItemView]:
    rows = db.execute(
        select(TodoItem, Topic, Chapter, Document, Subject)
        .join(Topic, Topic.id == TodoItem.topic_id)
        .join(Chapter, Chapter.id == Topic.chapter_id)
        .join(Document, Document.id == Chapter.document_id)
        .join(Subject, Subject.id == Document.subject_id)
        .order_by(TodoItem.created_at, TodoItem.id)
    ).all()
    return [
        TodoItemView(
            topic_id=topic.id,
            title=topic.title,
            chapter_title=chapter.title,
            document_id=document.id,
            document_filename=document.filename,
            subject_id=subject.id,
            subject_name=subject.name,
            studied=topic.studied,
            created_at=item.created_at,
        )
        for item, topic, chapter, document, subject in rows
    ]


def list_items(db: Session) -> list[TodoItemView]:
    """All to-do items in insertion order, labelled for display."""
    return _item_rows(db)


def add_topics(db: Session, topic_ids: list[int]) -> list[TodoItemView]:
    """Pin topics to the list (idempotent — already-pinned and unknown ids are
    skipped), then return the full refreshed list. Commits."""
    wanted = set(topic_ids)
    existing = set(
        db.scalars(select(TodoItem.topic_id).where(TodoItem.topic_id.in_(wanted)))
    )
    valid = set(db.scalars(select(Topic.id).where(Topic.id.in_(wanted - existing))))
    for topic_id in topic_ids:  # keep the caller's order for created_at ties
        if topic_id in valid:
            db.add(TodoItem(topic_id=topic_id))
            valid.discard(topic_id)
    db.commit()
    return _item_rows(db)


def remove_topic(db: Session, topic_id: int) -> bool:
    """Unpin one topic. Returns True if it was on the list."""
    item = db.scalar(select(TodoItem).where(TodoItem.topic_id == topic_id))
    if item is None:
        return False
    db.delete(item)
    db.commit()
    return True


def clear_completed(db: Session) -> int:
    """Remove every item whose topic is checked off (studied). Returns count."""
    studied_ids = select(Topic.id).where(Topic.studied.is_(True))
    result = db.execute(delete(TodoItem).where(TodoItem.topic_id.in_(studied_ids)))
    db.commit()
    return result.rowcount or 0
