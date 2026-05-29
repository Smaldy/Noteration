"""Stage 4 — Generation. Per-topic notes (7a) and assessment (7b).

Two model calls per topic (docs/ai-pipeline.md): call 1 = dense notes, call 2 =
MCQs + flashcards together (with the notes as context, so questions stay
consistent with the material). Calls go through the provider ``Waterfall`` so any
tier can serve them; the queue owns transactions, failover, and retry — these
processors only build the prompt, call the model, and write their domain rows
*uncommitted* (the queue commits atomically).

Per-topic source text is sliced from the document's cached markdown by matching
the topic title to a heading, falling back to the chapter section and then the
whole document (never zero context). See DECISIONS in docs/build-log.md.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import Chapter, Document, Flashcard, MCQ, Note, Topic
from backend.models.processing import QueueJob
from backend.services.pipeline.structure import _clean_title, iter_atx_headings
from backend.services.providers.base import ProviderResult
from backend.services.providers.waterfall import Waterfall

# Output caps — sized so a runaway generation can't burn quota (cost-strategy.md
# "token budgets per call"). Tunable per the benchmark later.
NOTES_MAX_TOKENS = 2048
ASSESSMENT_MAX_TOKENS = 2048

SourceLoader = Callable[[Session, Topic], str]


class TopicSourceUnavailableError(Exception):
    """The topic's document markdown could not be read (needs re-ingest)."""


class NotesContextMissingError(Exception):
    """Assessment was asked to run for a topic that has no notes yet."""


class AssessmentParseError(Exception):
    """The model's assessment output was not valid/usable JSON."""


def build_notes_prompt(topic_title: str, source_text: str) -> str:
    """Prompt for dense, engineer-level notes on one topic."""
    return (
        "You are an expert engineering tutor. Write dense, accurate, "
        "exam-useful study notes in Markdown for the topic below. Cover the key "
        "concepts, definitions, and formulas; be concise but complete; do not "
        "invent material that is not supported by the source.\n\n"
        f"# Topic\n{topic_title}\n\n"
        f"# Source material\n{source_text}\n"
    )


def load_topic_source(session: Session, topic: Topic) -> str:
    """Slice the topic's source markdown: topic section → chapter section → doc."""
    chapter = session.get(Chapter, topic.chapter_id)
    document = session.get(Document, chapter.document_id) if chapter else None
    if document is None or not document.markdown_path:
        raise TopicSourceUnavailableError(topic.id)
    path = Path(document.markdown_path)
    if not path.is_file():
        raise TopicSourceUnavailableError(str(path))
    markdown = path.read_text(encoding="utf-8")

    section = slice_section(markdown, topic.title)
    if section:
        return section
    if chapter is not None:
        section = slice_section(markdown, chapter.title)
        if section:
            return section
    return markdown.strip()


def slice_section(markdown: str, title: str) -> str | None:
    """Return the heading whose title matches ``title`` plus its body, or None.

    The body runs until the next heading of the same or shallower level, so a
    chapter slice includes its sub-topics and a topic slice stops at its sibling.
    """
    headings = iter_atx_headings(markdown)
    target = _clean_title(title).casefold()
    lines = markdown.splitlines(keepends=True)
    for index, (level, htitle, line_no) in enumerate(headings):
        if htitle.casefold() != target:
            continue
        end = len(lines)
        for next_level, _, next_line in headings[index + 1 :]:
            if next_level <= level:
                end = next_line
                break
        return "".join(lines[line_no:end]).strip()
    return None


def make_notes_processor(
    waterfall: Waterfall,
    *,
    source_loader: SourceLoader = load_topic_source,
    max_tokens: int = NOTES_MAX_TOKENS,
) -> Callable[[QueueJob, Session], ProviderResult]:
    """Build the queue ``StageProcessor`` for the notes stage."""

    def process(job: QueueJob, session: Session) -> ProviderResult:
        topic = session.get(Topic, job.topic_id)
        source = source_loader(session, topic)
        prompt = build_notes_prompt(topic.title, source)
        result = waterfall.generate(prompt, max_tokens=max_tokens)
        session.add(Note(topic_id=topic.id, content_md=result.text, is_manual=False))
        return result

    return process


# --- assessment (MCQs + flashcards) -----------------------------------------


@dataclass
class ParsedMCQ:
    question: str
    options: list[str]
    correct_index: int
    explanation: str = ""


@dataclass
class ParsedFlashcard:
    front: str
    back: str


@dataclass
class AssessmentData:
    mcqs: list[ParsedMCQ] = field(default_factory=list)
    flashcards: list[ParsedFlashcard] = field(default_factory=list)


def build_assessment_prompt(topic_title: str, notes_md: str) -> str:
    """Prompt for MCQs + flashcards as one JSON object, grounded in the notes."""
    return (
        "You are an expert engineering tutor. From the study notes below, create "
        "5-10 multiple-choice questions and 5-10 flashcards that test "
        "understanding of the material. Base everything strictly on the notes.\n\n"
        "Respond with ONLY a JSON object of this exact shape (no prose, no code "
        "fences):\n"
        '{"mcqs": [{"question": str, "options": [str, ...], '
        '"correct_index": int, "explanation": str}], '
        '"flashcards": [{"front": str, "back": str}]}\n'
        "Each MCQ must have at least 2 options and a correct_index that points to "
        "the right option.\n\n"
        f"# Topic\n{topic_title}\n\n"
        f"# Notes\n{notes_md}\n"
    )


def parse_assessment(text: str) -> AssessmentData:
    """Parse + validate the model's assessment JSON. Raises on malformed output."""
    raw = _extract_json_object(text)
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError) as exc:
        raise AssessmentParseError(f"not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise AssessmentParseError("top-level JSON is not an object")

    mcqs = [_parse_mcq(item) for item in data.get("mcqs", [])]
    flashcards = [_parse_flashcard(item) for item in data.get("flashcards", [])]
    if not mcqs or not flashcards:
        raise AssessmentParseError("expected at least one MCQ and one flashcard")
    return AssessmentData(mcqs=mcqs, flashcards=flashcards)


def make_assessment_processor(
    waterfall: Waterfall,
    *,
    max_tokens: int = ASSESSMENT_MAX_TOKENS,
) -> Callable[[QueueJob, Session], ProviderResult]:
    """Build the queue ``StageProcessor`` for the assessment stage."""

    def process(job: QueueJob, session: Session) -> ProviderResult:
        topic = session.get(Topic, job.topic_id)
        notes_md = _latest_ai_notes(session, topic)
        prompt = build_assessment_prompt(topic.title, notes_md)
        result = waterfall.generate(prompt, max_tokens=max_tokens)
        parsed = parse_assessment(result.text)
        for mcq in parsed.mcqs:
            session.add(
                MCQ(
                    topic_id=topic.id,
                    question=mcq.question,
                    options=mcq.options,
                    correct_index=mcq.correct_index,
                    explanation=mcq.explanation,
                    is_manual=False,
                )
            )
        for card in parsed.flashcards:
            # Flashcards start at SM-2 defaults (ease 2.5, interval/reps 0).
            session.add(
                Flashcard(
                    topic_id=topic.id, front=card.front, back=card.back, is_manual=False
                )
            )
        return result

    return process


def _latest_ai_notes(session: Session, topic: Topic) -> str:
    note = session.scalars(
        select(Note)
        .where(Note.topic_id == topic.id, Note.is_manual.is_(False))
        .order_by(Note.id.desc())
    ).first()
    if note is None:
        raise NotesContextMissingError(topic.id)
    return note.content_md


def _extract_json_object(text: str) -> str:
    """Pull the JSON object out of a model response (tolerates fences/prose)."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise AssessmentParseError("no JSON object found in response")
    return text[start : end + 1]


def _parse_mcq(item: object) -> ParsedMCQ:
    if not isinstance(item, dict):
        raise AssessmentParseError("MCQ is not an object")
    question = _require_str(item.get("question"), "MCQ.question")
    options = item.get("options")
    if not isinstance(options, list) or len(options) < 2:
        raise AssessmentParseError("MCQ.options must be a list of >= 2 choices")
    options = [_require_str(opt, "MCQ.option") for opt in options]
    correct = item.get("correct_index")
    if not isinstance(correct, int) or isinstance(correct, bool):
        raise AssessmentParseError("MCQ.correct_index must be an integer")
    if not 0 <= correct < len(options):
        raise AssessmentParseError("MCQ.correct_index out of range")
    explanation = item.get("explanation", "")
    if not isinstance(explanation, str):
        raise AssessmentParseError("MCQ.explanation must be a string")
    return ParsedMCQ(question, options, correct, explanation)


def _parse_flashcard(item: object) -> ParsedFlashcard:
    if not isinstance(item, dict):
        raise AssessmentParseError("flashcard is not an object")
    return ParsedFlashcard(
        front=_require_str(item.get("front"), "flashcard.front"),
        back=_require_str(item.get("back"), "flashcard.back"),
    )


def _require_str(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AssessmentParseError(f"{label} must be a non-empty string")
    return value
