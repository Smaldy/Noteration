"""Topic service — read a topic's generated content for the Study View."""

from __future__ import annotations

from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.models import MCQ, Flashcard, Formula, Note, QueueJob, Topic
from backend.models.enums import DocumentMode, QueueStage
from backend.services.attachments import attachment_url
from backend.services.pipeline.formula import (
    NO_OP_PROVIDER,
    transcribe_pending_formulas,
)
from backend.services.pipeline.generation import (
    GENERATE_MORE_MAX_TOKENS,
    MORE_FLASHCARDS_SCHEMA,
    MORE_MCQS_SCHEMA,
    NOTES_ONLY_SCHEMA,
    build_more_flashcards_prompt,
    build_more_mcqs_prompt,
    build_regenerate_notes_prompt,
    clamp_note_length,
    get_or_create_ai_note,
    load_topic_source,
    normalize_language,
    notes_only_max_tokens,
    parse_more_flashcards,
    parse_more_mcqs,
    parse_notes_only,
    source_cap_for,
    topic_document_mode,
)
from backend.services.providers.factory import build_waterfall_from_settings
from backend.services.providers.waterfall import Waterfall
from backend.services.settings import get_settings

GenerateMoreKind = Literal["mcqs", "flashcards"]


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


class NoteLockedError(Exception):
    """The topic's AI note is locked, so it must not be regenerated."""


class NotesNotSupportedError(Exception):
    """This document is exam-only — it has no notes to regenerate."""


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
            selectinload(Topic.attachments),
        )
    ).scalar_one_or_none()
    if topic is None:
        raise TopicNotFoundError(topic_id)
    # Transient provenance stamp (point 14): which provider generated this topic.
    topic.generated_by = _generating_provider(session, topic_id)
    # Stamp each attachment's serve URL (derived, not stored) for the schema.
    for attachment in topic.attachments:
        attachment.url = attachment_url(attachment)
    return topic


def _generating_provider(session: Session, topic_id: int) -> str | None:
    """The provider that ran this topic's generation (notes) stage, if any real one."""
    provider = session.scalar(
        select(QueueJob.assigned_provider).where(
            QueueJob.topic_id == topic_id,
            QueueJob.stage == QueueStage.notes,
        )
    )
    return provider if provider and provider != NO_OP_PROVIDER else None


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


def generate_more(
    session: Session,
    topic_id: int,
    kind: GenerateMoreKind,
    *,
    waterfall: Waterfall | None = None,
) -> int:
    """Generate ADDITIONAL MCQs or flashcards for a topic, on demand.

    A user-triggered, synchronous single model call (like formula transcription —
    it does not go through the background queue). Grounds the call in the topic's
    source and lists existing items so the model produces *new* ones, then appends
    the parsed rows and commits. Returns the number added.

    Raises ``TopicNotFoundError`` for an unknown topic; ``TopicSourceUnavailableError``
    when the document markdown is missing; provider-exhaustion and parse errors
    propagate for the router to map to 503/502. ``waterfall`` is injectable for tests.
    """
    topic = session.get(Topic, topic_id)
    if topic is None:
        raise TopicNotFoundError(topic_id)
    settings = get_settings(session)
    if waterfall is None:
        waterfall = build_waterfall_from_settings(settings)
    language = normalize_language(settings.language)

    source = load_topic_source(session, topic)
    if kind == "mcqs":
        existing = list(
            session.scalars(select(MCQ.question).where(MCQ.topic_id == topic_id))
        )
        prompt = build_more_mcqs_prompt(topic.title, source, existing, language=language)
        result = waterfall.generate(
            prompt, max_tokens=GENERATE_MORE_MAX_TOKENS, response_schema=MORE_MCQS_SCHEMA
        )
        added = 0
        for mcq in parse_more_mcqs(result.text):
            session.add(
                MCQ(
                    topic_id=topic_id,
                    question=mcq.question,
                    options=mcq.options,
                    correct_index=mcq.correct_index,
                    explanation=mcq.explanation,
                    is_manual=False,
                )
            )
            added += 1
    else:
        existing = list(
            session.scalars(select(Flashcard.front).where(Flashcard.topic_id == topic_id))
        )
        prompt = build_more_flashcards_prompt(
            topic.title, source, existing, language=language
        )
        result = waterfall.generate(
            prompt,
            max_tokens=GENERATE_MORE_MAX_TOKENS,
            response_schema=MORE_FLASHCARDS_SCHEMA,
        )
        added = 0
        for card in parse_more_flashcards(result.text):
            session.add(
                Flashcard(
                    topic_id=topic_id, front=card.front, back=card.back, is_manual=False
                )
            )
            added += 1
    session.commit()
    return added


def regenerate_notes(
    session: Session,
    topic_id: int,
    *,
    instructions: str | None = None,
    waterfall: Waterfall | None = None,
) -> None:
    """Regenerate a topic's AI notes when the current ones don't satisfy the user.

    A user-triggered, synchronous single model call (like ``generate_more`` /
    formula transcription — not the background queue). Rewrites ONLY the AI note's
    markdown from the topic's source, optionally steered by the reader's
    ``instructions`` (what to change). The quiz and flashcards are deliberately
    left untouched so MCQ progress and SM-2 review state survive; the AI note is
    marked ``stale`` to record that the assessment predates the new notes.

    Raises ``TopicNotFoundError`` (unknown topic), ``NotesNotSupportedError``
    (exam-mode doc has no notes), ``NoteLockedError`` (the note is locked against
    regeneration), ``TopicSourceUnavailableError`` (source markdown missing); the
    provider-exhaustion and parse errors propagate for the router to map.
    ``waterfall`` is injectable for tests.
    """
    topic = session.get(Topic, topic_id)
    if topic is None:
        raise TopicNotFoundError(topic_id)
    if topic_document_mode(session, topic) is DocumentMode.exam:
        raise NotesNotSupportedError(topic_id)
    # A locked AI note is protected from regeneration (see Note.locked).
    existing = session.scalars(
        select(Note)
        .where(Note.topic_id == topic_id, Note.is_manual.is_(False))
        .order_by(Note.id.desc())
    ).first()
    if existing is not None and existing.locked:
        raise NoteLockedError(topic_id)

    settings = get_settings(session)
    if waterfall is None:
        waterfall = build_waterfall_from_settings(settings)
    length = clamp_note_length(settings.note_length)
    language = normalize_language(settings.language)

    source = load_topic_source(session, topic, max_chars=source_cap_for(length))
    prompt = build_regenerate_notes_prompt(
        topic.title, source, note_length=length, language=language, instructions=instructions
    )
    result = waterfall.generate(
        prompt, max_tokens=notes_only_max_tokens(length), response_schema=NOTES_ONLY_SCHEMA
    )
    notes_md = parse_notes_only(result.text)

    note = get_or_create_ai_note(session, topic)
    note.content_md = notes_md
    # The assessment was generated alongside the previous notes; flag the drift.
    note.stale = True
    _restamp_notes_provider(session, topic_id, result.provider)
    session.commit()


def _restamp_notes_provider(session: Session, topic_id: int, provider: str) -> None:
    """Update the notes-stage job's provider stamp after a manual regeneration.

    Keeps the Study View's "generated by" provenance accurate when a regeneration
    is served by a different provider than the original background run. No-op for
    no-op/empty provider names or topics without a notes job.
    """
    if not provider or provider == NO_OP_PROVIDER:
        return
    job = session.scalars(
        select(QueueJob).where(
            QueueJob.topic_id == topic_id, QueueJob.stage == QueueStage.notes
        )
    ).first()
    if job is not None:
        job.assigned_provider = provider


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
