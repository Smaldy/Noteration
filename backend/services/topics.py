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
