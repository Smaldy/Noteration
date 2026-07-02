"""Topic service — read a topic's generated content for the Study View."""

from __future__ import annotations

from datetime import date
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.models import (
    MCQ,
    Flashcard,
    Formula,
    Note,
    QueueJob,
    Subject,
    Topic,
)
from backend.models.enums import DocumentMode, QueueStage
from backend.services import scheduler
from backend.services.attachments import attachment_url
from backend.services.pipeline.formula import (
    NO_OP_PROVIDER,
    transcribe_pending_formulas,
)
from backend.services.pipeline.generation import (
    CONSOLIDATE_NOTES_MAX_TOKENS,
    GENERATE_MORE_MAX_TOKENS,
    MORE_FLASHCARDS_SCHEMA,
    MORE_MCQS_SCHEMA,
    NOTES_ONLY_SCHEMA,
    build_consolidate_notes_prompt,
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
    existing = _latest_ai_note(session, topic_id)
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


def _latest_ai_note(session: Session, topic_id: int) -> Note | None:
    """The topic's current AI note (the one regeneration/merge would touch)."""
    return session.scalars(
        select(Note)
        .where(Note.topic_id == topic_id, Note.is_manual.is_(False))
        .order_by(Note.id.desc())
    ).first()


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


class InvalidMergeError(ValueError):
    """The merge request is unusable (no sources besides the target itself)."""


def merge_topics(
    session: Session,
    target_id: int,
    source_ids: list[int],
    *,
    consolidate: bool = False,
    waterfall: Waterfall | None = None,
    today: date | None = None,
) -> bool:
    """Merge ``source_ids``' content into the target topic; delete the sources.

    The fix for per-lesson PDFs piling up parallel topics on one subject: works
    across chapters and documents (any topic can absorb any other). MCQs,
    flashcards, and attachments are *re-pointed*, so quiz progress and SM-2
    review state travel untouched; manual notes move as-is; each source's AI
    note is appended to the target's AI note under a heading named for the
    source topic. Same-document page-mapped topics union their ``pdf_pages`` so
    a later regeneration sees the combined slides. The emptied source topics are
    deleted (cascading their queue jobs and schedule entries) and every affected
    subject's calendar is rebuilt so moved flashcards reschedule immediately.

    ``consolidate=True`` additionally spends ONE model call rewriting the
    combined notes into a deduplicated document — best-effort: on provider
    exhaustion or unusable output the concatenation stands (locked or exam-mode
    notes always skip it). Returns whether consolidation ran. The merge itself
    is committed before that call.
    """
    target = session.get(Topic, target_id)
    if target is None:
        raise TopicNotFoundError(target_id)
    ids = [i for i in dict.fromkeys(source_ids) if i != target_id]
    if not ids:
        raise InvalidMergeError(target_id)
    found = {
        topic.id: topic
        for topic in session.execute(
            select(Topic)
            .where(Topic.id.in_(ids))
            .options(
                selectinload(Topic.mcqs),
                selectinload(Topic.flashcards),
                selectinload(Topic.attachments),
                selectinload(Topic.notes),
            )
        ).scalars()
    }
    missing = [i for i in ids if i not in found]
    if missing:
        raise TopicNotFoundError(missing[0])
    sources = [found[i] for i in ids]

    merged_note = _append_source_notes(session, target, sources)

    # Assessment rows carry their own progress/SM-2 state; re-parenting moves
    # them without touching it. Manual notes and attachments likewise. Done at
    # the ORM level (not a bulk UPDATE) so the relationship collections stay in
    # sync and deleting the source can't cascade over the moved rows.
    for source in sources:
        for row in [*source.mcqs, *source.flashcards, *source.attachments]:
            row.topic = target
        for note in list(source.notes):
            if note.is_manual:
                note.topic = target
    _union_pdf_pages(target, sources)

    subjects = _affected_subjects(target, sources)
    for source in sources:
        session.delete(source)
    session.flush()

    when = today if today is not None else date.today()
    for subject in subjects:
        scheduler.rebuild_schedule(session, subject, today=when)
    # Commit the merge before any model call: consolidation is best-effort and
    # must not hold the SQLite write lock across a network round-trip.
    session.commit()

    if not (consolidate and merged_note is not None):
        return False
    consolidated = _consolidate_notes(session, target, merged_note, waterfall)
    if consolidated:
        session.commit()
    return consolidated


def _append_source_notes(
    session: Session, target: Topic, sources: list[Topic]
) -> Note | None:
    """Append each source's AI note to the target's, headed by the source title.

    Returns the target's AI note when anything was appended (the consolidation
    candidate), else ``None``. A locked target note is never rewritten — the
    lock means "don't touch this text" (see ``regenerate_notes``) — so the
    source AI notes are re-pointed to the target as their own notes instead:
    their content survives the merge without editing the locked one.
    """
    moved = [
        (source, note)
        for source in sources
        for note in source.notes
        if not note.is_manual and note.content_md.strip()
    ]
    if not moved:
        return None

    existing = _latest_ai_note(session, target.id)
    if existing is not None and existing.locked:
        for source, note in moved:
            note.content_md = f"## {source.title}\n\n{note.content_md.strip()}"
            note.topic = target
        return None

    note = existing if existing is not None else get_or_create_ai_note(session, target)
    sections = [
        f"## {source.title}\n\n{src_note.content_md.strip()}"
        for source, src_note in moved
    ]
    current = note.content_md.strip()
    note.content_md = "\n\n".join(([current] if current else []) + sections)
    return note


def _union_pdf_pages(target: Topic, sources: list[Topic]) -> None:
    """Union same-document sources' page lists into the target's.

    Deliberately asymmetric: pages merge only when the *target* already has
    them and the source lives in the same document — pages from another PDF
    would index the wrong file, and a page-less target has no page-mapped
    source slice to extend.
    """
    if not target.pdf_pages:
        return
    document_id = target.chapter.document_id
    pages = set(target.pdf_pages)
    for source in sources:
        if source.chapter.document_id == document_id and source.pdf_pages:
            pages.update(source.pdf_pages)
    target.pdf_pages = sorted(pages)


def _affected_subjects(target: Topic, sources: list[Topic]) -> list[Subject]:
    """Every distinct subject touched by the merge (target + sources)."""
    return list({topic.chapter.subject for topic in [target, *sources]})


def _consolidate_notes(
    session: Session, target: Topic, note: Note, waterfall: Waterfall | None
) -> bool:
    """Best-effort AI rewrite of the target's concatenated notes. True if it ran."""
    if topic_document_mode(session, target) is DocumentMode.exam:
        return False
    if note.locked or not note.content_md.strip():
        return False

    settings = get_settings(session)
    if waterfall is None:
        waterfall = build_waterfall_from_settings(settings)
    prompt = build_consolidate_notes_prompt(
        target.title,
        note.content_md,
        language=normalize_language(settings.language),
    )
    try:
        result = waterfall.generate(
            prompt,
            max_tokens=CONSOLIDATE_NOTES_MAX_TOKENS,
            response_schema=NOTES_ONLY_SCHEMA,
        )
        note.content_md = parse_notes_only(result.text)
    except Exception:  # noqa: BLE001 - the concatenated notes are a fine fallback
        return False
    _restamp_notes_provider(session, target.id, result.provider)
    return True


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
