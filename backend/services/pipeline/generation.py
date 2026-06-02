"""Stage 4 — Generation. Per-topic notes + assessment in ONE model call.

The pipeline originally made two calls per topic (notes, then MCQs+flashcards with
the notes re-sent as context). On the Gemini free tier that second call's input —
the full generated notes — doubled token spend and burned a second request against
the per-minute quota for no quality gain. We now collapse both into a **single
structured-output call**: one prompt returns one JSON object carrying ``notes_md``
plus the MCQ/flashcard arrays, validated against ``GENERATION_SCHEMA`` (Gemini
native JSON Schema). The notes never leave for a second round trip.

(This supersedes ai-pipeline.md's "two calls is the floor" — a deliberate,
user-directed cost change; see docs/build-log.md DECISIONS.)

Calls go through the provider ``Waterfall`` so any tier can serve them; the queue
owns transactions, failover, and retry — this processor only builds the prompt,
calls the model, parses, and writes its domain rows *uncommitted* (the queue
commits atomically).

Per-topic source text is sliced from the document's cached markdown by matching
the topic title to a heading, falling back to the chapter section and then a
bounded proportional slice (never zero context, never the whole doc per topic).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import Chapter, Document, Flashcard, MCQ, Note, Topic
from backend.models.enums import DocumentMode
from backend.models.processing import QueueJob
from backend.services.pipeline.structure import _clean_title, iter_atx_headings
from backend.services.providers.base import ProviderResult
from backend.services.providers.waterfall import Waterfall

# Output cap — sized so one runaway generation can't burn quota (cost-strategy.md
# "token budgets per call"). One call now carries both notes and the assessment,
# so the cap is the sum of the old two (~2k notes + ~2k assessment). Tunable later.
GENERATION_MAX_TOKENS = 4096
# Exam mode drops notes but asks for ~10-15 MCQs + ~10-15 flashcards (denser
# practice), so it needs more output headroom than the notes+5-10-each study call.
EXAM_GENERATION_MAX_TOKENS = 6144

# Input cap on the per-topic source text sent to the model. The dominant cost
# driver is INPUT tokens (a 22-page PDF is ~14k tokens), and a single topic never
# needs the whole document as context. This bounds the per-call input cost
# regardless of slicing path (cost-strategy.md "token budgets per call") and is
# the safety net for documents whose markdown has no headings to slice by —
# scanned/slide PDFs, or topics renamed during review. ~8k chars ≈ 2k tokens.
SOURCE_MAX_CHARS = 8000
# A little context carried across proportional-slice boundaries so a topic isn't
# cut off mid-paragraph when there are no headings to slice on.
SOURCE_OVERLAP_CHARS = 400

SourceLoader = Callable[[Session, Topic], str]


class TopicSourceUnavailableError(Exception):
    """The topic's document markdown could not be read (needs re-ingest)."""


class GenerationParseError(Exception):
    """The model's generation output was not valid/usable JSON."""


# JSON Schema handed to Gemini's native structured output so the single call
# returns one object with the notes and the assessment together. Providers
# without native schema support (Claude) lean on the prompt's JSON instruction;
# ``parse_generation`` validates the result either way.
GENERATION_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "notes_md": {"type": "string"},
        "mcqs": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "options": {"type": "array", "items": {"type": "string"}},
                    "correct_index": {"type": "integer"},
                    "explanation": {"type": "string"},
                },
                "required": ["question", "options", "correct_index", "explanation"],
            },
        },
        "flashcards": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "front": {"type": "string"},
                    "back": {"type": "string"},
                },
                "required": ["front", "back"],
            },
        },
    },
    "required": ["notes_md", "mcqs", "flashcards"],
}

# Exam-mode schema: assessment only, no notes. The MCQ/flashcard item shapes are
# identical to the study schema so parsing/validation is shared.
EXAM_GENERATION_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "mcqs": GENERATION_SCHEMA["properties"]["mcqs"],
        "flashcards": GENERATION_SCHEMA["properties"]["flashcards"],
    },
    "required": ["mcqs", "flashcards"],
}


def build_generation_prompt(
    topic_title: str,
    source_text: str,
    *,
    mode: DocumentMode = DocumentMode.study,
) -> str:
    """Prompt for the single generation call, grounded in the topic's source.

    In ``study`` mode this asks for notes + an aligned assessment in one JSON
    object so the notes never have to be re-sent as context for a second call. In
    ``exam`` mode (the Exam Prep section) it drops notes entirely and asks for a
    denser assessment. The shape is spelled out inline so providers without native
    JSON-schema support still return the right structure.
    """
    if mode is DocumentMode.exam:
        return (
            "You are an expert engineering tutor preparing a student for an exam. "
            "From the source material for ONE topic, produce a thorough assessment "
            "of the material as a single JSON object.\n\n"
            "Respond with ONLY a JSON object of this exact shape (no prose, no code "
            "fences):\n"
            '{"mcqs": [{"question": str, "options": [str, ...], '
            '"correct_index": int, "explanation": str}], '
            '"flashcards": [{"front": str, "back": str}]}\n'
            "- mcqs: 10-15 exam-style multiple-choice questions grounded in the "
            "source; each with at least 2 options, a correct_index pointing to the "
            "right option, and a clear explanation of why it is correct.\n"
            "- flashcards: 10-15 flashcards grounded in the source.\n"
            "- Do not invent material the source does not support.\n\n"
            f"# Topic\n{topic_title}\n\n"
            f"# Source material\n{source_text}\n"
        )
    return (
        "You are an expert engineering tutor. From the source material for ONE "
        "topic, produce BOTH dense, exam-useful study notes AND an assessment of "
        "the material, in a single JSON object.\n\n"
        "Respond with ONLY a JSON object of this exact shape (no prose, no code "
        "fences):\n"
        '{"notes_md": str, '
        '"mcqs": [{"question": str, "options": [str, ...], '
        '"correct_index": int, "explanation": str}], '
        '"flashcards": [{"front": str, "back": str}]}\n'
        "- notes_md: Markdown notes covering the key concepts, definitions, and "
        "formulas; concise but complete; do not invent material the source does "
        "not support.\n"
        "- mcqs: 5-10 multiple-choice questions grounded in the notes; each with "
        "at least 2 options and a correct_index pointing to the right option.\n"
        "- flashcards: 5-10 flashcards grounded in the notes.\n\n"
        f"# Topic\n{topic_title}\n\n"
        f"# Source material\n{source_text}\n"
    )


def get_or_create_ai_note(session: Session, topic: Topic) -> Note:
    """Return the topic's AI note, creating an empty one if needed (flushed).

    Shared by the formula stage (attaches Formula rows) and the notes stage
    (fills ``content_md``) so both operate on the same Note — see DECISIONS.
    """
    note = session.scalars(
        select(Note)
        .where(Note.topic_id == topic.id, Note.is_manual.is_(False))
        .order_by(Note.id.desc())
    ).first()
    if note is None:
        note = Note(topic_id=topic.id, content_md="", is_manual=False)
        session.add(note)
        session.flush()
    return note


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
        return _cap_source(section)
    if chapter is not None:
        section = slice_section(markdown, chapter.title)
        if section:
            return _cap_source(section)
    # No heading matched the topic or its chapter — e.g. a headingless PDF
    # (scanned/slide decks, or markitdown output with no ATX structure) or a
    # topic renamed during review. Returning the WHOLE document here made every
    # topic re-send the entire file, which exhausts the token budget (a 13-topic
    # 14k-token doc cost ~180k input tokens). Give the topic its proportional
    # contiguous slice instead — see DECISIONS in docs/build-log.md.
    return _proportional_slice(session, document, topic, markdown)


def _cap_source(text: str, *, max_chars: int = SOURCE_MAX_CHARS) -> str:
    """Strip and hard-cap source text so no single call can blow the budget."""
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip()


def _ordered_topic_ids(session: Session, document: Document) -> list[int]:
    """Topic ids for a document in reading order (chapter then topic order)."""
    rows = session.execute(
        select(Topic.id)
        .join(Chapter, Topic.chapter_id == Chapter.id)
        .where(Chapter.document_id == document.id)
        .order_by(Chapter.order_index, Chapter.id, Topic.order_index, Topic.id)
    ).all()
    return [row[0] for row in rows]


def _proportional_slice(
    session: Session, document: Document, topic: Topic, markdown: str
) -> str:
    """Give ``topic`` its share of ``markdown`` by position among the doc's topics.

    Without headings we can't locate a topic's exact text, so we assume topics
    were defined in reading order and hand each one a contiguous window of the
    document (with a little overlap). A single-topic document still gets the whole
    (capped) text — that's one call, not N.
    """
    ordered = _ordered_topic_ids(session, document)
    count = len(ordered)
    if count <= 1:
        return _cap_source(markdown)
    try:
        index = ordered.index(topic.id)
    except ValueError:
        index = 0
    total = len(markdown)
    window = total / count
    start = max(0, int(index * window) - SOURCE_OVERLAP_CHARS)
    end = min(total, int((index + 1) * window) + SOURCE_OVERLAP_CHARS)
    return _cap_source(markdown[start:end])


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


# --- consolidated generation (notes + MCQs + flashcards in one call) --------


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
class GenerationData:
    """One topic's full generated output from the single model call."""

    notes_md: str
    mcqs: list[ParsedMCQ] = field(default_factory=list)
    flashcards: list[ParsedFlashcard] = field(default_factory=list)


def parse_generation(text: str, *, require_notes: bool = True) -> GenerationData:
    """Parse + validate the combined generation JSON. Raises on malformed output.

    ``require_notes=False`` (exam mode) makes ``notes_md`` optional — exam-mode
    output is assessment-only, so a missing/empty notes field is fine and any
    value present is ignored (``notes_md`` comes back as "").
    """
    raw = _extract_json_object(text)
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError) as exc:
        raise GenerationParseError(f"not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise GenerationParseError("top-level JSON is not an object")

    if require_notes:
        notes_md = _require_str(data.get("notes_md"), "notes_md")
    else:
        notes_md = ""
    mcqs = [_parse_mcq(item) for item in _as_list(data.get("mcqs"), "mcqs")]
    flashcards = [
        _parse_flashcard(item) for item in _as_list(data.get("flashcards"), "flashcards")
    ]
    if not mcqs or not flashcards:
        raise GenerationParseError("expected at least one MCQ and one flashcard")
    return GenerationData(notes_md=notes_md, mcqs=mcqs, flashcards=flashcards)


def topic_document_mode(session: Session, topic: Topic) -> DocumentMode:
    """Resolve a topic's document mode (study | exam), defaulting to study."""
    chapter = session.get(Chapter, topic.chapter_id)
    document = session.get(Document, chapter.document_id) if chapter else None
    return document.mode if document is not None else DocumentMode.study


# --- on-demand "generate more" (user-triggered, single kind) ----------------

# Smaller cap than the full generation call — one kind, ~8-12 items.
GENERATE_MORE_MAX_TOKENS = 2048
# Bound how many existing items we list back to the model (anti-duplication) so
# the prompt can't itself blow the input budget on a topic with a huge bank.
_MAX_EXISTING_LISTED = 40

# Single-kind schemas (reuse the item shapes from the full generation schema).
MORE_MCQS_SCHEMA: dict = {
    "type": "object",
    "properties": {"mcqs": GENERATION_SCHEMA["properties"]["mcqs"]},
    "required": ["mcqs"],
}
MORE_FLASHCARDS_SCHEMA: dict = {
    "type": "object",
    "properties": {"flashcards": GENERATION_SCHEMA["properties"]["flashcards"]},
    "required": ["flashcards"],
}


def _existing_block(label: str, items: list[str]) -> str:
    """A 'do not repeat these' block listing existing items (capped)."""
    listed = [item.strip() for item in items if item and item.strip()][
        :_MAX_EXISTING_LISTED
    ]
    if not listed:
        return ""
    body = "\n".join(f"- {item}" for item in listed)
    return f"\n# Already covered {label} (do NOT repeat or rephrase these)\n{body}\n"


def build_more_mcqs_prompt(
    topic_title: str, source_text: str, existing_questions: list[str]
) -> str:
    """Prompt for ADDITIONAL MCQs only, distinct from the existing ones."""
    return (
        "You are an expert engineering tutor. Write ADDITIONAL exam-style "
        "multiple-choice questions for ONE topic, grounded in the source material "
        "and DISTINCT from the questions already written.\n\n"
        "Respond with ONLY a JSON object of this exact shape (no prose, no code "
        'fences):\n{"mcqs": [{"question": str, "options": [str, ...], '
        '"correct_index": int, "explanation": str}]}\n'
        "- 8-12 NEW questions; each with at least 2 options, a correct_index "
        "pointing to the right option, and a clear explanation.\n"
        "- Do not invent material the source does not support.\n"
        f"{_existing_block('questions', existing_questions)}"
        f"\n# Topic\n{topic_title}\n\n# Source material\n{source_text}\n"
    )


def build_more_flashcards_prompt(
    topic_title: str, source_text: str, existing_fronts: list[str]
) -> str:
    """Prompt for ADDITIONAL flashcards only, distinct from the existing ones."""
    return (
        "You are an expert engineering tutor. Write ADDITIONAL flashcards for ONE "
        "topic, grounded in the source material and DISTINCT from the flashcards "
        "already written.\n\n"
        "Respond with ONLY a JSON object of this exact shape (no prose, no code "
        'fences):\n{"flashcards": [{"front": str, "back": str}]}\n'
        "- 8-12 NEW flashcards.\n"
        "- Do not invent material the source does not support.\n"
        f"{_existing_block('flashcard fronts', existing_fronts)}"
        f"\n# Topic\n{topic_title}\n\n# Source material\n{source_text}\n"
    )


def _load_object(text: str) -> dict:
    """Parse a model response into a JSON object or raise GenerationParseError."""
    raw = _extract_json_object(text)
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError) as exc:
        raise GenerationParseError(f"not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise GenerationParseError("top-level JSON is not an object")
    return data


def parse_more_mcqs(text: str) -> list[ParsedMCQ]:
    """Parse a single-kind MCQ response. Raises if no usable MCQ is present."""
    data = _load_object(text)
    mcqs = [_parse_mcq(item) for item in _as_list(data.get("mcqs"), "mcqs")]
    if not mcqs:
        raise GenerationParseError("expected at least one MCQ")
    return mcqs


def parse_more_flashcards(text: str) -> list[ParsedFlashcard]:
    """Parse a single-kind flashcard response. Raises if none are present."""
    data = _load_object(text)
    cards = [
        _parse_flashcard(item) for item in _as_list(data.get("flashcards"), "flashcards")
    ]
    if not cards:
        raise GenerationParseError("expected at least one flashcard")
    return cards


def make_generation_processor(
    waterfall: Waterfall,
    *,
    source_loader: SourceLoader = load_topic_source,
    max_tokens: int = GENERATION_MAX_TOKENS,
    exam_max_tokens: int = EXAM_GENERATION_MAX_TOKENS,
) -> Callable[[QueueJob, Session], ProviderResult]:
    """Build the queue ``StageProcessor`` for the consolidated generation stage.

    In study mode one call returns notes + assessment as a single JSON object (no
    second round trip re-sending the notes); the Note (shared with the formula
    stage) is filled and the MCQ/flashcard rows are added. In exam mode (the Exam
    Prep section) the call is assessment-only: no Note is written, just MCQs +
    flashcards. Either way the rows are added uncommitted; the queue commits the
    whole stage atomically.
    """

    def process(job: QueueJob, session: Session) -> ProviderResult:
        topic = session.get(Topic, job.topic_id)
        mode = topic_document_mode(session, topic)
        is_exam = mode is DocumentMode.exam
        source = source_loader(session, topic)
        prompt = build_generation_prompt(topic.title, source, mode=mode)
        result = waterfall.generate(
            prompt,
            max_tokens=exam_max_tokens if is_exam else max_tokens,
            response_schema=EXAM_GENERATION_SCHEMA if is_exam else GENERATION_SCHEMA,
        )
        parsed = parse_generation(result.text, require_notes=not is_exam)
        if not is_exam:
            note = get_or_create_ai_note(session, topic)
            note.content_md = parsed.notes_md
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


def _as_list(value: object, label: str) -> list:
    if value is None:
        return []
    if not isinstance(value, list):
        raise GenerationParseError(f"{label} must be a list")
    return value


def _extract_json_object(text: str) -> str:
    """Pull the JSON object out of a model response (tolerates fences/prose)."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise GenerationParseError("no JSON object found in response")
    return text[start : end + 1]


def _parse_mcq(item: object) -> ParsedMCQ:
    if not isinstance(item, dict):
        raise GenerationParseError("MCQ is not an object")
    question = _require_str(item.get("question"), "MCQ.question")
    options = item.get("options")
    if not isinstance(options, list) or len(options) < 2:
        raise GenerationParseError("MCQ.options must be a list of >= 2 choices")
    options = [_require_str(opt, "MCQ.option") for opt in options]
    correct = item.get("correct_index")
    if not isinstance(correct, int) or isinstance(correct, bool):
        raise GenerationParseError("MCQ.correct_index must be an integer")
    if not 0 <= correct < len(options):
        raise GenerationParseError("MCQ.correct_index out of range")
    explanation = item.get("explanation", "")
    if not isinstance(explanation, str):
        raise GenerationParseError("MCQ.explanation must be a string")
    return ParsedMCQ(question, options, correct, explanation)


def _parse_flashcard(item: object) -> ParsedFlashcard:
    if not isinstance(item, dict):
        raise GenerationParseError("flashcard is not an object")
    return ParsedFlashcard(
        front=_require_str(item.get("front"), "flashcard.front"),
        back=_require_str(item.get("back"), "flashcard.back"),
    )


def _require_str(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GenerationParseError(f"{label} must be a non-empty string")
    return value
