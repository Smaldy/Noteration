"""Stage 4 — Generation. Sub-wave 7a: per-topic notes.

Two model calls per topic (docs/ai-pipeline.md): call 1 = dense notes (here),
call 2 = MCQs + flashcards (a later sub-wave). Calls go through the provider
``Waterfall`` so any tier can serve them; the queue owns transactions, failover,
and retry — these processors only build the prompt, call the model, and write
their domain rows *uncommitted* (the queue commits atomically).

Per-topic source text is sliced from the document's cached markdown by matching
the topic title to a heading, falling back to the chapter section and then the
whole document (never zero context). See DECISIONS in docs/build-log.md.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from sqlalchemy.orm import Session

from backend.models import Chapter, Document, Note, Topic
from backend.models.processing import QueueJob
from backend.services.pipeline.structure import _clean_title, iter_atx_headings
from backend.services.providers.base import ProviderResult
from backend.services.providers.waterfall import Waterfall

# Output cap for the notes call — sized so a runaway generation can't burn quota
# (cost-strategy.md "token budgets per call"). Tunable per the benchmark later.
NOTES_MAX_TOKENS = 2048

SourceLoader = Callable[[Session, Topic], str]


class TopicSourceUnavailableError(Exception):
    """The topic's document markdown could not be read (needs re-ingest)."""


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
