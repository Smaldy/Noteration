"""Topic service — read a topic's generated content for the Study View."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.models import Note, Topic


class TopicNotFoundError(LookupError):
    """Referenced topic does not exist."""


def get_topic_content(session: Session, topic_id: int) -> Topic:
    """Load a topic with its notes (+formulas), MCQs, and flashcards eagerly.

    Returns the ORM ``Topic``; the router serializes it via ``TopicContentOut``.
    Eager-loads to avoid an N+1 while Pydantic walks the relationships.
    """
    topic = session.execute(
        select(Topic)
        .where(Topic.id == topic_id)
        .options(
            selectinload(Topic.notes).selectinload(Note.formulas),
            selectinload(Topic.mcqs),
            selectinload(Topic.flashcards),
        )
    ).scalar_one_or_none()
    if topic is None:
        raise TopicNotFoundError(topic_id)
    return topic


def set_bookmark(session: Session, topic_id: int, *, bookmarked: bool) -> Topic:
    """Set a topic's bookmark flag. Raises ``TopicNotFoundError`` if missing."""
    topic = session.get(Topic, topic_id)
    if topic is None:
        raise TopicNotFoundError(topic_id)
    topic.bookmarked = bookmarked
    session.commit()
    session.refresh(topic)
    return topic


def delete_topic(session: Session, topic_id: int) -> None:
    """Delete a topic and everything generated from it.

    ORM + DB cascade remove the topic's notes (and their formulas), MCQs,
    flashcards, queue jobs, schedule entries, and source pages. Raises
    ``TopicNotFoundError`` if it does not exist.
    """
    topic = session.get(Topic, topic_id)
    if topic is None:
        raise TopicNotFoundError(topic_id)
    session.delete(topic)
    session.commit()
