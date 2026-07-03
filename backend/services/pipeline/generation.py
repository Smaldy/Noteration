"""Stage 4 — Generation. Per-topic notes + assessment in ONE model call.

The pipeline originally made two calls per topic (notes, then MCQs+flashcards with
the notes re-sent as context). On the Gemini free tier that second call's input —
the full generated notes — doubled token spend and burned a second request against
the per-minute quota for no quality gain. We now collapse both into a **single
structured-output call**: one prompt returns one JSON object carrying ``notes_md``
plus the MCQ/flashcard arrays, validated against ``GENERATION_SCHEMA`` (Gemini
native JSON Schema). The notes never leave for a second round trip.

(This supersedes the original two-calls-per-topic design — a deliberate,
user-directed cost change; see docs/architecture.md (Design decisions).)

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

from backend.models import MCQ, Chapter, Document, Flashcard, Note, Topic
from backend.models.enums import DocumentMode
from backend.models.processing import QueueJob
from backend.paths import UPLOADS_DIR
from backend.services.pipeline.ingestion import (
    get_chapter_markdown,
    get_pages_markdown,
)
from backend.services.pipeline.structure import _clean_title, iter_atx_headings
from backend.services.providers.base import ProviderResult
from backend.services.providers.waterfall import Waterfall
from backend.services.settings import get_settings

# Notes "length" — how much notes content to generate per topic, in *pages*
# (units of content). The user picks 1-10 in Settings (``Settings.note_length``);
# the model is asked to aim for that many pages and to produce only what the
# source genuinely supports when there isn't enough material (never pad/invent).
MIN_NOTE_LENGTH = 1
MAX_NOTE_LENGTH = 10
DEFAULT_NOTE_LENGTH = 3
# A "page" of notes ≈ this many words; drives the prompt's word target.
WORDS_PER_PAGE = 300

# Output cap — sized so one runaway generation can't burn quota (docs/architecture.md
# "token budgets per call"). One call carries both notes and the assessment. The
# assessment half is roughly fixed; the notes half scales with the requested page
# count so longer notes aren't truncated mid-page. These are *ceilings* — the
# prompt drives the actual length. At the default 3 pages this is ~4k, matching
# the previous flat cap.
ASSESSMENT_OUTPUT_TOKENS = 2048
NOTES_OUTPUT_TOKENS_PER_PAGE = 650
# Back-compat default (3 pages); callers can still pass an explicit ``max_tokens``.
GENERATION_MAX_TOKENS = ASSESSMENT_OUTPUT_TOKENS + DEFAULT_NOTE_LENGTH * NOTES_OUTPUT_TOKENS_PER_PAGE
# Exam mode drops notes but asks for ~10-15 MCQs + ~10-15 flashcards (denser
# practice), so it needs more output headroom than the notes+5-10-each study call.
EXAM_GENERATION_MAX_TOKENS = 6144

# Input cap on the per-topic source text sent to the model. The dominant cost
# driver is INPUT tokens (a 22-page PDF is ~14k tokens), and a single topic never
# needs the whole document as context. This bounds the per-call input cost
# regardless of slicing path (docs/architecture.md "token budgets per call") and is
# the safety net for documents whose markdown has no headings to slice by —
# scanned/slide PDFs, or topics renamed during review. ~8k chars ≈ 2k tokens.
SOURCE_MAX_CHARS = 8000
# More requested note pages pull a larger slice of the topic's source so the
# model has enough material to expand into longer notes; fewer pages need less
# context (cheaper). Scales with ``note_length`` and is bounded both ways so the
# dominant (input) cost stays in check. At the default 3 pages this is ~7.8k,
# matching the previous flat ``SOURCE_MAX_CHARS`` cap.
SOURCE_CHARS_PER_PAGE = 2600
# A little context carried across proportional-slice boundaries so a topic isn't
# cut off mid-paragraph when there are no headings to slice on.
SOURCE_OVERLAP_CHARS = 400

SourceLoader = Callable[[Session, Topic], str]

# --- output language --------------------------------------------------------
# The user picks the app language in Settings (Settings.language); new generated
# content (notes, MCQs, flashcards) is produced in that language. English is the
# default and adds no directive (the prompts are already English). For Italian /
# Spanish a directive is appended instructing the model to write all *content* in
# that language — the JSON keys and LaTeX/math notation stay unchanged.
DEFAULT_LANGUAGE = "en"
LANGUAGE_NAMES: dict[str, str] = {"en": "English", "it": "Italian", "es": "Spanish"}


def normalize_language(code: str | None) -> str:
    """Coerce a language code to a supported one, defaulting to English."""
    return code if code in LANGUAGE_NAMES else DEFAULT_LANGUAGE


def language_directive(language: str) -> str:
    """Prompt block instructing the output language, or "" for English.

    Targets the *content* only: every human-readable value (notes, questions,
    options, explanations, card fronts/backs) must be in the chosen language,
    while the JSON object keys and LaTeX/math notation are left as-is.
    """
    language = normalize_language(language)
    if language == DEFAULT_LANGUAGE:
        return ""
    name = LANGUAGE_NAMES[language]
    return (
        f"\n# Output language\nWrite ALL human-readable content — the notes, "
        f"questions, answer options, explanations, and flashcard fronts and backs "
        f"— in {name}. Translate naturally into {name}; do not answer in English. "
        f"Keep the JSON field names exactly as specified (in English) and leave "
        f"mathematical notation, LaTeX, formulas, symbols, and code unchanged.\n"
    )


# --- student profile (field of study) ---------------------------------------
# The prompts used to hardcode "an expert engineering tutor", which skews the
# output toward formulas and derivations even for a literature or law student.
# ``Settings.study_field`` now picks a discipline profile: the tutor persona
# opening every prompt, plus what "complete notes" means in that field (the
# coverage line — an engineering topic wants formulas; a humanities topic wants
# themes, authors, and context). "general" is deliberately neutral.


@dataclass(frozen=True)
class FieldProfile:
    """One discipline's prompt flavor: the tutor persona + notes coverage."""

    persona: str  # "an expert engineering tutor" — opens every prompt
    coverage: str  # what the notes must cover in this field


DEFAULT_STUDY_FIELD = "general"

STUDY_FIELDS: dict[str, FieldProfile] = {
    "general": FieldProfile(
        persona="an expert tutor",
        coverage="the key concepts, definitions, and essential facts",
    ),
    "engineering": FieldProfile(
        # Matches the previously hardcoded persona/coverage exactly, so an
        # engineering student's prompts are unchanged by this feature.
        persona="an expert engineering tutor",
        coverage="the key concepts, definitions, and formulas",
    ),
    "mathematics": FieldProfile(
        persona="an expert mathematics tutor",
        coverage="the key definitions, theorems, proofs, and worked examples",
    ),
    "natural_sciences": FieldProfile(
        persona="an expert natural-sciences tutor",
        coverage="the key concepts, mechanisms, processes, and experimental evidence",
    ),
    "medicine": FieldProfile(
        persona="an expert medicine and health-sciences tutor",
        coverage=(
            "the key concepts, mechanisms, classifications, and their clinical "
            "relevance"
        ),
    ),
    "law": FieldProfile(
        persona="an expert law tutor",
        coverage=(
            "the key principles, definitions, statutes, leading cases, and "
            "exceptions"
        ),
    ),
    "economics": FieldProfile(
        persona="an expert economics and business tutor",
        coverage="the key concepts, models, assumptions, and real-world examples",
    ),
    "humanities": FieldProfile(
        persona="an expert humanities tutor (literature, history, philosophy)",
        coverage=(
            "the key themes, arguments, authors, works, dates, and historical "
            "context"
        ),
    ),
    "languages": FieldProfile(
        persona="an expert language tutor",
        coverage=(
            "the key vocabulary, grammar rules, usage patterns, and example "
            "sentences"
        ),
    ),
}


def normalize_study_field(field: str | None) -> str:
    """Coerce a study field to a supported one, defaulting to "general"."""
    return field if field in STUDY_FIELDS else DEFAULT_STUDY_FIELD


def field_profile(study_field: str | None) -> FieldProfile:
    """The discipline profile for a (possibly unknown) study field."""
    return STUDY_FIELDS[normalize_study_field(study_field)]


# --- writing style ------------------------------------------------------------
# ``Settings.ai_style`` steers HOW the model words everything it generates —
# notes, MCQ explanations, flashcards. "balanced" is the default and adds no
# directive (prompts identical to before the setting existed); every other
# style appends a "# Writing style" block, mirroring ``language_directive``.

DEFAULT_AI_STYLE = "balanced"

AI_STYLES: dict[str, str] = {
    "balanced": "",
    "simple": (
        "Explain everything in plain, everyday wording as if to a beginner: "
        "short sentences, define each technical term the first time it "
        "appears, and use intuitive examples or analogies. Prefer clarity "
        "over brevity."
    ),
    "technical": (
        "Write for an advanced student: use precise, field-standard "
        "terminology and rigorous, formal statements; keep full technical "
        "depth and do not simplify detail away. Skip beginner analogies."
    ),
    "discursive": (
        "Write in a discursive, flowing style: connected paragraphs that walk "
        "through the reasoning and link ideas together, as if explaining "
        "aloud. Prefer prose over bullet lists (this overrides the list-first "
        "formatting rule); keep lists only for genuinely enumerable items."
    ),
    "concise": (
        "Be as compact as possible: prefer bullet points and short "
        "declarative sentences over prose; no filler, hedging, or "
        "restatement — every line must carry new information."
    ),
    "academic": (
        "Write in a formal academic register: professional, impersonal tone, "
        "precise wording, and well-structured argumentation; no "
        "colloquialisms."
    ),
}


def normalize_ai_style(style: str | None) -> str:
    """Coerce a writing style to a supported one, defaulting to "balanced"."""
    return style if style in AI_STYLES else DEFAULT_AI_STYLE


def style_directive(ai_style: str | None) -> str:
    """Prompt block steering the writing style, or "" for the default.

    Applies to ALL generated human-readable content — the wording of notes,
    questions, explanations, and flashcards — not to the JSON structure.
    """
    text = AI_STYLES[normalize_ai_style(ai_style)]
    if not text:
        return ""
    return (
        "\n# Writing style\nApply this style to all generated content (notes, "
        f"explanations, flashcards):\n{text}\n"
    )


def clamp_note_length(note_length: int) -> int:
    """Clamp a requested note length into the supported 1-10 page range."""
    return max(MIN_NOTE_LENGTH, min(MAX_NOTE_LENGTH, note_length))


def study_max_tokens(note_length: int) -> int:
    """Output-token ceiling for a study generation call at this note length."""
    return ASSESSMENT_OUTPUT_TOKENS + clamp_note_length(note_length) * NOTES_OUTPUT_TOKENS_PER_PAGE


def source_cap_for(note_length: int) -> int:
    """Per-call source (input) character ceiling for this note length."""
    return clamp_note_length(note_length) * SOURCE_CHARS_PER_PAGE


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


# Static Markdown formatting rules for generated notes, shared by the full
# generation call and the on-demand notes regeneration so they can't drift apart.
# The (variable) length rule is prepended separately by ``_notes_length_rule``.
_NOTES_FORMAT_RULES = (
    "  * Organise with `##` and `###` headings and short paragraphs; separate "
    "every heading, paragraph, and list with a blank line.\n"
    "  * Use `-` bullet lists for enumerations and key points; use numbered "
    "lists only for ordered steps.\n"
    "  * Write normal prose. Use `**bold**` ONLY to emphasise a key term or "
    "definition (a few words) — never bold whole sentences, lines, or the "
    "entire note. Use `*italics*` sparingly.\n"
    "  * Put math in LaTeX: `$inline$` and `$$display$$`.\n"
    "  * Do NOT wrap the notes in a code fence.\n"
)

# Math rule for the assessment fields (mcq question/options/explanation,
# flashcard front/back). Without this the model often emits bare or `\(…\)`-style
# math, which the renderer can't typeset — so exponents and integrals show up as
# literal `10^3` / `\int` text. The `$…$` form is what the front-end expects.
_ASSESSMENT_MATH_RULE = (
    "- Math: in every question, option, explanation, and flashcard, write ALL "
    r"mathematical notation as LaTeX delimited with `$inline$` (or `$$display$$`), "
    r"e.g. `$10^3$`, `$n^x$`, `$\int_0^1 x^2\,dx$` — never bare or `\(...\)`-style."
    "\n"
)


def _notes_length_rule(note_length: int) -> str:
    """The 'aim for N pages' length directive for the notes formatting block."""
    pages = clamp_note_length(note_length)
    words = pages * WORDS_PER_PAGE
    return (
        f"  * Length: aim for about {pages} page{'s' if pages != 1 else ''} of "
        f"notes (~{words} words). If the source doesn't contain enough material "
        "for that, write only what the source genuinely supports — never pad, "
        "repeat, or invent content to reach the target.\n"
    )


def build_generation_prompt(
    topic_title: str,
    source_text: str,
    *,
    mode: DocumentMode = DocumentMode.study,
    note_length: int = DEFAULT_NOTE_LENGTH,
    language: str = DEFAULT_LANGUAGE,
    study_field: str = DEFAULT_STUDY_FIELD,
    ai_style: str = DEFAULT_AI_STYLE,
) -> str:
    """Prompt for the single generation call, grounded in the topic's source.

    In ``study`` mode this asks for notes + an aligned assessment in one JSON
    object so the notes never have to be re-sent as context for a second call;
    ``note_length`` (1-10 pages) sets how much notes content to aim for. In
    ``exam`` mode (the Exam Prep section) it drops notes entirely (``note_length``
    is ignored) and asks for a denser assessment. The shape is spelled out inline
    so providers without native JSON-schema support still return the right
    structure. ``language`` (en|it|es) sets the language of the generated content;
    English adds no directive. ``study_field`` picks the tutor persona and notes
    coverage for the student's discipline; ``ai_style`` steers the wording
    ("balanced" adds no directive).
    """
    lang_rule = language_directive(language)
    length_rule = _notes_length_rule(note_length)
    profile = field_profile(study_field)
    style_rule = style_directive(ai_style)
    if mode is DocumentMode.exam:
        return (
            f"You are {profile.persona} preparing a student for an exam. "
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
            f"{_ASSESSMENT_MATH_RULE}"
            "- Do not invent material the source does not support.\n"
            f"{style_rule}{lang_rule}\n"
            f"# Topic\n{topic_title}\n\n"
            f"# Source material\n{source_text}\n"
        )
    return (
        f"You are {profile.persona}. From the source material for ONE "
        "topic, produce BOTH dense, exam-useful study notes AND an assessment of "
        "the material, in a single JSON object.\n\n"
        "Respond with ONLY a JSON object of this exact shape (no prose, no code "
        "fences):\n"
        '{"notes_md": str, '
        '"mcqs": [{"question": str, "options": [str, ...], '
        '"correct_index": int, "explanation": str}], '
        '"flashcards": [{"front": str, "back": str}]}\n'
        f"- notes_md: Well-structured Markdown notes covering {profile.coverage}; "
        "concise but complete; do not invent material "
        "the source does not support. Formatting rules (follow exactly):\n"
        f"{length_rule}"
        f"{_NOTES_FORMAT_RULES}"
        "- mcqs: 5-10 multiple-choice questions grounded in the notes; each with "
        "at least 2 options and a correct_index pointing to the right option.\n"
        "- flashcards: 5-10 flashcards grounded in the notes.\n"
        f"{_ASSESSMENT_MATH_RULE}"
        f"{style_rule}{lang_rule}\n"
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


def load_topic_source(
    session: Session, topic: Topic, *, max_chars: int = SOURCE_MAX_CHARS
) -> str:
    """Slice the topic's source markdown.

    Page-mapped topic (``source_pages`` set — slide decks) → convert **exactly
    those pages** (cached per run): a merged multi-slide topic gets its real
    slides' text, not a proportional guess. Outline-backed chapter (``page_start``
    set) → **lazy per-chapter markdown**: convert only the chapter's pages
    (cached), then slice the topic's heading within that chapter — so a 700-page
    book never loads the whole document for one topic. Otherwise (headingless /
    no outline) → the existing whole-document path: topic section → chapter
    section → proportional slice.

    ``max_chars`` hard-caps the returned text (the dominant input-cost lever); it
    scales with the requested note length so longer notes get more context.
    """
    chapter = session.get(Chapter, topic.chapter_id)
    document = session.get(Document, chapter.document_id) if chapter else None
    if document is None:
        raise TopicSourceUnavailableError(topic.id)

    if topic.pdf_pages and document.file_hash:
        pdf_path = UPLOADS_DIR / f"{document.file_hash}.pdf"
        if pdf_path.is_file():
            pages_md = get_pages_markdown(
                pdf_path, document.file_hash, topic.pdf_pages
            )
            if pages_md.strip():
                return _cap_source(pages_md, max_chars=max_chars)
        # Missing PDF or empty conversion (image-only slides) → the generic paths
        # below still provide non-zero context.

    if (
        chapter is not None
        and chapter.page_start is not None
        and chapter.page_end is not None
    ):
        return _load_chapter_scoped_source(
            session, document, chapter, topic, max_chars=max_chars
        )

    if not document.markdown_path:
        raise TopicSourceUnavailableError(topic.id)
    path = Path(document.markdown_path)
    if not path.is_file():
        raise TopicSourceUnavailableError(str(path))
    markdown = path.read_text(encoding="utf-8")

    section = slice_section(markdown, topic.title)
    if section:
        return _cap_source(section, max_chars=max_chars)
    if chapter is not None:
        section = slice_section(markdown, chapter.title)
        if section:
            return _cap_source(section, max_chars=max_chars)
    # No heading matched the topic or its chapter — e.g. a headingless PDF
    # (scanned/slide decks, or markitdown output with no ATX structure) or a
    # topic renamed during review. Returning the WHOLE document here made every
    # topic re-send the entire file, which exhausts the token budget (a 13-topic
    # 14k-token doc cost ~180k input tokens). Give the topic its proportional
    # contiguous slice instead — see docs/architecture.md (Design decisions).
    ordered = _ordered_topic_ids(session, document)
    return _cap_source(
        _proportional_window(ordered, topic.id, markdown), max_chars=max_chars
    )


def _load_chapter_scoped_source(
    session: Session,
    document: Document,
    chapter: Chapter,
    topic: Topic,
    *,
    max_chars: int = SOURCE_MAX_CHARS,
) -> str:
    """Source for a topic in an outline-backed chapter, scoped to that chapter.

    Convert just the chapter's page range (cached on disk), then slice the topic's
    heading within the chapter markdown; if no heading matches, give the topic a
    proportional slice over the *chapter* markdown only (never the whole document).
    """
    pdf_path = UPLOADS_DIR / f"{document.file_hash}.pdf"
    if not document.file_hash or not pdf_path.is_file():
        raise TopicSourceUnavailableError(str(pdf_path))

    chapter_md = get_chapter_markdown(
        pdf_path,
        document.file_hash,
        chapter.page_start,
        chapter.page_end,
    )
    section = slice_section(chapter_md, topic.title)
    if section:
        return _cap_source(section, max_chars=max_chars)
    ordered = _ordered_chapter_topic_ids(session, chapter)
    return _cap_source(
        _proportional_window(ordered, topic.id, chapter_md), max_chars=max_chars
    )


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


def _ordered_chapter_topic_ids(session: Session, chapter: Chapter) -> list[int]:
    """Topic ids within one chapter in reading order."""
    rows = session.execute(
        select(Topic.id)
        .where(Topic.chapter_id == chapter.id)
        .order_by(Topic.order_index, Topic.id)
    ).all()
    return [row[0] for row in rows]


def _proportional_window(ordered_ids: list[int], topic_id: int, markdown: str) -> str:
    """Give ``topic_id`` its share of ``markdown`` by position among ``ordered_ids``.

    Without headings we can't locate a topic's exact text, so we assume topics were
    defined in reading order and hand each one a contiguous window (with a little
    overlap). A single id (or unknown id) gets the whole text — one call, not N.
    The caller applies ``_cap_source``.
    """
    count = len(ordered_ids)
    if count <= 1:
        return markdown
    try:
        index = ordered_ids.index(topic_id)
    except ValueError:
        index = 0
    total = len(markdown)
    window = total / count
    start = max(0, int(index * window) - SOURCE_OVERLAP_CHARS)
    end = min(total, int((index + 1) * window) + SOURCE_OVERLAP_CHARS)
    return markdown[start:end]


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
    topic_title: str,
    source_text: str,
    existing_questions: list[str],
    *,
    language: str = DEFAULT_LANGUAGE,
    study_field: str = DEFAULT_STUDY_FIELD,
    ai_style: str = DEFAULT_AI_STYLE,
) -> str:
    """Prompt for ADDITIONAL MCQs only, distinct from the existing ones."""
    return (
        f"You are {field_profile(study_field).persona}. Write ADDITIONAL exam-style "
        "multiple-choice questions for ONE topic, grounded in the source material "
        "and DISTINCT from the questions already written.\n\n"
        "Respond with ONLY a JSON object of this exact shape (no prose, no code "
        'fences):\n{"mcqs": [{"question": str, "options": [str, ...], '
        '"correct_index": int, "explanation": str}]}\n'
        "- 8-12 NEW questions; each with at least 2 options, a correct_index "
        "pointing to the right option, and a clear explanation.\n"
        "- Do not invent material the source does not support.\n"
        f"{style_directive(ai_style)}"
        f"{language_directive(language)}"
        f"{_existing_block('questions', existing_questions)}"
        f"\n# Topic\n{topic_title}\n\n# Source material\n{source_text}\n"
    )


def build_more_flashcards_prompt(
    topic_title: str,
    source_text: str,
    existing_fronts: list[str],
    *,
    language: str = DEFAULT_LANGUAGE,
    study_field: str = DEFAULT_STUDY_FIELD,
    ai_style: str = DEFAULT_AI_STYLE,
) -> str:
    """Prompt for ADDITIONAL flashcards only, distinct from the existing ones."""
    return (
        f"You are {field_profile(study_field).persona}. Write ADDITIONAL flashcards for ONE "
        "topic, grounded in the source material and DISTINCT from the flashcards "
        "already written.\n\n"
        "Respond with ONLY a JSON object of this exact shape (no prose, no code "
        'fences):\n{"flashcards": [{"front": str, "back": str}]}\n'
        "- 8-12 NEW flashcards.\n"
        "- Do not invent material the source does not support.\n"
        f"{style_directive(ai_style)}"
        f"{language_directive(language)}"
        f"{_existing_block('flashcard fronts', existing_fronts)}"
        f"\n# Topic\n{topic_title}\n\n# Source material\n{source_text}\n"
    )


# --- on-demand notes regeneration (user-triggered, notes only) --------------

# Schema for the notes-only regeneration call: just the rewritten Markdown. The
# assessment (MCQs/flashcards) is deliberately NOT regenerated so the user's quiz
# and SM-2 flashcard review state survive a notes rewrite.
NOTES_ONLY_SCHEMA: dict = {
    "type": "object",
    "properties": {"notes_md": {"type": "string"}},
    "required": ["notes_md"],
}


def notes_only_max_tokens(note_length: int) -> int:
    """Output-token ceiling for a notes-only regeneration at this note length.

    Cheaper than a full generation call — no assessment tokens, just the notes
    half of ``study_max_tokens``.
    """
    return clamp_note_length(note_length) * NOTES_OUTPUT_TOKENS_PER_PAGE


def build_regenerate_notes_prompt(
    topic_title: str,
    source_text: str,
    *,
    note_length: int = DEFAULT_NOTE_LENGTH,
    language: str = DEFAULT_LANGUAGE,
    study_field: str = DEFAULT_STUDY_FIELD,
    ai_style: str = DEFAULT_AI_STYLE,
    instructions: str | None = None,
) -> str:
    """Prompt to rewrite ONE topic's notes from its source, optionally guided.

    Returns a single ``{"notes_md": str}`` object (no assessment). When the reader
    gives ``instructions`` (what they didn't like / want changed), they're added as
    a steering block so a regeneration actually differs from the first pass —
    still grounded in the source, never inventing material.
    """
    feedback_block = ""
    if instructions and instructions.strip():
        feedback_block = (
            "\n# What to improve\nThe previous notes did not satisfy the reader. "
            "Apply this feedback when rewriting, while staying grounded in the "
            "source and never inventing material the source does not support:\n"
            f"{instructions.strip()}\n"
        )
    profile = field_profile(study_field)
    return (
        f"You are {profile.persona}. Rewrite the study notes for ONE "
        "topic from the source material as a fresh, improved version, returned as "
        "a single JSON object.\n\n"
        "Respond with ONLY a JSON object of this exact shape (no prose, no code "
        'fences):\n{"notes_md": str}\n'
        f"- notes_md: Well-structured Markdown notes covering {profile.coverage}; "
        "concise but complete; do not invent material "
        "the source does not support. Formatting rules (follow exactly):\n"
        f"{_notes_length_rule(note_length)}"
        f"{_NOTES_FORMAT_RULES}"
        f"{style_directive(ai_style)}"
        f"{language_directive(language)}"
        f"{feedback_block}"
        f"\n# Topic\n{topic_title}\n\n# Source material\n{source_text}\n"
    )


# Output ceiling for a merged-notes consolidation: the input is several topics'
# notes, so the rewrite needs more headroom than a single regeneration; still a
# ceiling, not a target — the prompt asks for deduplication, not expansion.
CONSOLIDATE_NOTES_MAX_TOKENS = 8192


def build_consolidate_notes_prompt(
    topic_title: str,
    notes_md: str,
    *,
    language: str = DEFAULT_LANGUAGE,
    study_field: str = DEFAULT_STUDY_FIELD,
    ai_style: str = DEFAULT_AI_STYLE,
) -> str:
    """Prompt to rewrite a merged topic's concatenated notes as ONE document.

    Used after a topic merge: the input is the target's notes plus each source
    topic's notes appended under a heading — overlapping by construction (the
    user merged them *because* they cover the same subject). The model dedupes
    and reorganizes; it must not invent material or drop content that appears in
    only one of the merged notes. Returns ``{"notes_md": str}`` like the
    regeneration call (``NOTES_ONLY_SCHEMA`` / ``parse_notes_only``).
    """
    return (
        f"You are {field_profile(study_field).persona}. The study notes below were merged "
        "from several overlapping note sets about the same subject. Rewrite them "
        "as ONE coherent, deduplicated set of notes, returned as a single JSON "
        "object.\n\n"
        "Respond with ONLY a JSON object of this exact shape (no prose, no code "
        'fences):\n{"notes_md": str}\n'
        "- notes_md: the merged notes as well-structured Markdown. Combine "
        "duplicated explanations into one; keep every concept, definition, "
        "formula, and example that appears in ANY of the note sets; do not "
        "invent new material. Formatting rules (follow exactly):\n"
        f"{_NOTES_FORMAT_RULES}"
        f"{style_directive(ai_style)}"
        f"{language_directive(language)}"
        f"\n# Topic\n{topic_title}\n\n# Notes to merge\n{notes_md}\n"
    )


def parse_notes_only(text: str) -> str:
    """Parse a notes-only regeneration response → the notes markdown.

    Raises ``GenerationParseError`` if ``notes_md`` is missing or empty.
    """
    data = _load_object(text)
    return _require_str(data.get("notes_md"), "notes_md")


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


def _resolve_note_length(session: Session) -> int:
    """The user's configured notes length (1-10 pages), clamped."""
    return clamp_note_length(get_settings(session).note_length)


def _resolve_language(session: Session) -> str:
    """The user's configured output language (en|it|es), normalized."""
    return normalize_language(get_settings(session).language)


def _resolve_study_field(session: Session) -> str:
    """The user's configured field of study, normalized."""
    return normalize_study_field(get_settings(session).study_field)


def _resolve_ai_style(session: Session) -> str:
    """The user's configured writing style, normalized."""
    return normalize_ai_style(get_settings(session).ai_style)


def make_generation_processor(
    waterfall: Waterfall,
    *,
    source_loader: SourceLoader = load_topic_source,
    note_length: int | None = None,
    language: str | None = None,
    study_field: str | None = None,
    ai_style: str | None = None,
    max_tokens: int | None = None,
    exam_max_tokens: int = EXAM_GENERATION_MAX_TOKENS,
) -> Callable[[QueueJob, Session], ProviderResult]:
    """Build the queue ``StageProcessor`` for the consolidated generation stage.

    In study mode one call returns notes + assessment as a single JSON object (no
    second round trip re-sending the notes); the Note (shared with the formula
    stage) is filled and the MCQ/flashcard rows are added. In exam mode (the Exam
    Prep section) the call is assessment-only: no Note is written, just MCQs +
    flashcards. Either way the rows are added uncommitted; the queue commits the
    whole stage atomically.

    ``note_length`` (1-10 pages) sets how much notes content to generate and scales
    both the per-call source window and the output-token ceiling; ``None`` reads it
    from ``Settings`` per job so a change in Settings takes effect on the next job
    without rebuilding the processor. ``language`` (en|it|es) sets the generated
    content's language; ``None`` reads it from ``Settings`` per job (same rationale
    as ``note_length`` — not a provider-identity concern, so no cache rebuild).
    ``study_field`` and ``ai_style`` steer the tutor persona / notes coverage and
    the writing style; ``None`` likewise reads them from ``Settings`` per job.
    ``max_tokens`` overrides the computed study ceiling when given.
    """

    def process(job: QueueJob, session: Session) -> ProviderResult:
        topic = session.get(Topic, job.topic_id)
        mode = topic_document_mode(session, topic)
        is_exam = mode is DocumentMode.exam
        length = note_length if note_length is not None else _resolve_note_length(session)
        lang = language if language is not None else _resolve_language(session)
        field = study_field if study_field is not None else _resolve_study_field(session)
        style = ai_style if ai_style is not None else _resolve_ai_style(session)
        # Exam mode has no notes, so its source window stays at the fixed default;
        # study mode scales the window with the requested note length.
        if source_loader is load_topic_source:
            cap = SOURCE_MAX_CHARS if is_exam else source_cap_for(length)
            source = source_loader(session, topic, max_chars=cap)
        else:
            source = source_loader(session, topic)
        prompt = build_generation_prompt(
            topic.title,
            source,
            mode=mode,
            note_length=length,
            language=lang,
            study_field=field,
            ai_style=style,
        )
        study_cap = max_tokens if max_tokens is not None else study_max_tokens(length)
        result = waterfall.generate(
            prompt,
            max_tokens=exam_max_tokens if is_exam else study_cap,
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
