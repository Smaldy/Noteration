"""Topic service — read a topic's generated content for the Study View."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.models import Formula, Note, Topic
from backend.services.pipeline.formula import transcribe_pending_formulas
from backend.services.providers.factory import build_waterfall_from_settings
from backend.services.settings import get_settings


def reorder_topics(session: Session, ids: list[int]) -> None:
    """Set each listed topic's ``order_index`` to its position in ``ids``.

    Used to drag-reorder topics within a chapter; unknown ids are ignored.
    """
    found = {
        topic.id: topic
        for topic in session.execute(
            select(Topic).where(Topic.id.in_(ids))
        ).scalars()
    }
    for position, topic_id in enumerate(ids):
        topic = found.get(topic_id)
        if topic is not None:
            topic.order_index = position
    session.commit()


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


def transcribe_formulas(session: Session, topic_id: int) -> list[Formula]:
    """Lazily transcribe a topic's pending formulas via the vision waterfall.

    Triggered when a user opens a topic (the background queue only *registers*
    pending formula regions — it never spends vision budget). Builds the waterfall
    from the current ``Settings`` (so a freshly-saved key works), transcribes each
    pending region (re-cropped grayscale/150 DPI), and flips it to
    ``reconstructed``. Raises ``TopicNotFoundError`` for an unknown topic;
    provider-exhaustion errors propagate for the router to surface.
    """
    topic = session.get(Topic, topic_id)
    if topic is None:
        raise TopicNotFoundError(topic_id)
    waterfall = build_waterfall_from_settings(get_settings(session))
    return transcribe_pending_formulas(session, topic_id, waterfall)


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
