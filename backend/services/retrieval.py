"""Grounding retrieval for the assistant sidebar's reference topic.

When the user pins a topic to a chat session, its stored study material becomes
the reference the assistant answers from. That material is often far larger than
the prompt can hold, so this module answers two questions:

*What are the candidate pieces?*  The topic's notes are split into chunks — one
per markdown heading section, further split at paragraph boundaries when a
section runs long — each carrying its heading so a chunk still reads in context
once it's lifted out. Flashcards come last, as compact "key facts", and only if
budget remains. MCQs are deliberately excluded: they are assessment artifacts,
and feeding the model its own quiz questions invites it to parrot them back.

*Which pieces go in?*  The chunks are ranked with BM25 against the user's
message. The corpus is a single topic (tens of chunks, not millions), so a
keyword ranker beats embeddings here on every axis that matters: no model to
download, no index to keep in sync with SQLite, no cold-start latency, and it
stays local-first by construction. When the query carries no usable terms (an
emitter's "explain this" over a quoted card), ranking would be noise, so the
chunks are taken in document order instead — the topic read from the top.

Budgets are in characters, following the pipeline's existing ~4 chars/token
convention (see ``generation.SOURCE_MAX_CHARS``). The caller enforces the total
prompt ceiling; ``CONTEXT_MAX_CHARS`` is this module's share of it.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.content import Flashcard, Note
from backend.models.hierarchy import Topic

# The pinned topic's share of the prompt. ~8k chars ≈ 2k tokens — the same order
# as the generation pipeline's per-topic source cap.
CONTEXT_MAX_CHARS = 8_000

# A chunk is one heading section, or a run of paragraphs up to this size. Big
# enough to hold an argument, small enough that a hit doesn't spend the budget.
CHUNK_MAX_CHARS = 1_200

# Chunks shorter than this are structural leftovers (a stray heading, a bullet
# fragment) and are dropped rather than ranked.
MIN_CHUNK_CHARS = 24

# BM25 knobs — the standard defaults; nothing here is tuned to a specific corpus.
BM25_K1 = 1.5
BM25_B = 0.75

# Query terms carrying no topical signal. Kept deliberately small and limited to
# the app's three UI languages: IDF already suppresses terms common across the
# topic, so this list only has to catch words that are rare *within* a topic yet
# still meaningless (a single "the" in one chunk would otherwise score high).
STOPWORDS = frozenset(
    """
    a an and are as at be but by can do does for from had has have how i if in into is
    it its me my no not of on or so than that the their them then there these they this
    to was were what when where which who why will with you your
    al como con de del el en es esa ese eso esta este esto la las lo los me mi no o para
    pero por que qué se su sus te tu un una uno y
    che chi ci come con cosa da dei del della di e è gli i il in la le lo ma mi ne nel
    non o per perché più quale quando si sono su sul tra un una uno
    """.split()
)


@dataclass(frozen=True)
class Chunk:
    """One candidate passage: its text, its heading, and its document order."""

    order: int
    heading: str
    text: str

    @property
    def rendered(self) -> str:
        """The chunk as it appears in the prompt (heading restored)."""
        return f"### {self.heading}\n{self.text}" if self.heading else self.text


@dataclass(frozen=True)
class TopicContext:
    """The grounding block for one pinned topic."""

    topic_id: int
    # "Biology › cells.pdf › Cell transport › Osmosis" — where the material sits.
    path: str
    # The selected chunks, assembled in document order. May be "" for a topic
    # whose content hasn't been generated yet; the path alone still orients the
    # model, so an empty extract is not the same as no context at all.
    extract: str
    # How many chunks the topic offered, and how many made the budget.
    total_chunks: int
    used_chunks: int


def build_topic_context(
    session: Session,
    topic_id: int,
    *,
    query: str,
    max_chars: int = CONTEXT_MAX_CHARS,
) -> TopicContext | None:
    """Retrieve the pinned topic's most relevant material for ``query``.

    Returns ``None`` if the topic no longer exists (a pin outliving its topic is
    ordinary: the FK nulls out, but a concurrent delete can still race a send).
    """
    topic = session.get(Topic, topic_id)
    if topic is None:
        return None

    chunks = _collect_chunks(session, topic)
    selected = _select(chunks, query=query, max_chars=max_chars)
    extract = _assemble(selected, chunks)
    return TopicContext(
        topic_id=topic.id,
        path=_topic_path(topic),
        extract=extract,
        total_chunks=len(chunks),
        used_chunks=len(selected),
    )


def _topic_path(topic: Topic) -> str:
    """Subject › document › chapter › topic — the model's sense of place."""
    chapter = topic.chapter
    document = chapter.document
    parts = [document.subject.name, document.filename, chapter.title, topic.title]
    return " › ".join(p for p in parts if p)


# --- chunking ----------------------------------------------------------------


def _collect_chunks(session: Session, topic: Topic) -> list[Chunk]:
    """The topic's material as ranked-ready chunks, in document order."""
    notes = list(
        session.execute(
            select(Note).where(Note.topic_id == topic.id).order_by(Note.id)
        ).scalars()
    )
    chunks: list[Chunk] = []
    for note in notes:
        for heading, body in _split_sections(note.content_md):
            for piece in _split_paragraphs(body):
                if len(piece) >= MIN_CHUNK_CHARS:
                    chunks.append(Chunk(len(chunks), heading, piece))

    # Flashcards are the topic's distilled facts — worth having when the notes
    # leave room, and the only material at all for a card-only topic.
    cards = list(
        session.execute(
            select(Flashcard)
            .where(Flashcard.topic_id == topic.id)
            .order_by(Flashcard.id)
        ).scalars()
    )
    for card in cards:
        text = f"{card.front.strip()} — {card.back.strip()}"
        if len(text) >= MIN_CHUNK_CHARS:
            chunks.append(Chunk(len(chunks), "Key facts", text))
    return chunks


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


def _split_sections(markdown: str) -> list[tuple[str, str]]:
    """Split markdown into (heading, body) sections, preserving order.

    Text before the first heading is a section with an empty heading.
    """
    sections: list[tuple[str, list[str]]] = [("", [])]
    for line in markdown.splitlines():
        match = _HEADING_RE.match(line)
        if match:
            sections.append((match.group(2).strip(), []))
        else:
            sections[-1][1].append(line)
    return [(heading, "\n".join(lines).strip()) for heading, lines in sections]


def _split_paragraphs(body: str) -> list[str]:
    """Pack a section's paragraphs into pieces of at most ``CHUNK_MAX_CHARS``.

    A single paragraph longer than the cap is kept whole rather than cut
    mid-sentence: an over-long chunk simply competes for the budget as one item.
    """
    if not body:
        return []
    if len(body) <= CHUNK_MAX_CHARS:
        return [body]

    pieces: list[str] = []
    current: list[str] = []
    size = 0
    for para in re.split(r"\n\s*\n", body):
        para = para.strip()
        if not para:
            continue
        if current and size + len(para) > CHUNK_MAX_CHARS:
            pieces.append("\n\n".join(current))
            current, size = [], 0
        current.append(para)
        size += len(para) + 2
    if current:
        pieces.append("\n\n".join(current))
    return pieces


# --- ranking -----------------------------------------------------------------

_WORD_RE = re.compile(r"\w+", re.UNICODE)


def _terms(text: str) -> list[str]:
    """Lowercased content words: no stopwords, nothing shorter than two chars."""
    words = _WORD_RE.findall(text.lower())
    return [w for w in words if len(w) > 1 and w not in STOPWORDS]


def _query_terms(query: str) -> list[str]:
    """Terms from the user's message, quote markers stripped.

    An emitter's turn arrives as ``> quoted source`` + an instruction; the quote
    is the best signal in it, so only the ``>`` prefix is dropped, not the text.
    """
    unquoted = "\n".join(
        re.sub(r"^\s*>\s?", "", line) for line in query.splitlines()
    )
    return _terms(unquoted)


def _select(chunks: list[Chunk], *, query: str, max_chars: int) -> list[Chunk]:
    """Fill the budget with the best chunks (BM25), or the first ones in order."""
    if not chunks:
        return []
    scores = _bm25(chunks, _query_terms(query))
    if any(score > 0 for score in scores):
        order = sorted(
            range(len(chunks)), key=lambda i: (-scores[i], chunks[i].order)
        )
    else:
        # No lexical signal (e.g. "explain this"): read the topic from the top.
        order = list(range(len(chunks)))

    selected: list[Chunk] = []
    used = 0
    for i in order:
        cost = len(chunks[i].rendered) + 2  # the joining blank line
        if used + cost > max_chars:
            # A chunk that doesn't fit is skipped, not a stop signal — a smaller
            # one further down the ranking may still earn its place.
            continue
        selected.append(chunks[i])
        used += cost
    return sorted(selected, key=lambda c: c.order)


def _bm25(chunks: list[Chunk], query: list[str]) -> list[float]:
    """Standard BM25 over the topic's own chunks as the corpus."""
    if not query:
        return [0.0] * len(chunks)

    docs = [_terms(c.rendered) for c in chunks]
    lengths = [len(d) for d in docs]
    avg_len = sum(lengths) / len(docs) if any(lengths) else 1.0
    n = len(docs)

    scores = [0.0] * n
    for term in set(query):
        df = sum(1 for d in docs if term in d)
        if df == 0:
            continue
        idf = math.log(1 + (n - df + 0.5) / (df + 0.5))
        for i, doc in enumerate(docs):
            tf = doc.count(term)
            if tf == 0:
                continue
            norm = 1 - BM25_B + BM25_B * (lengths[i] / avg_len if avg_len else 1)
            scores[i] += idf * (tf * (BM25_K1 + 1)) / (tf + BM25_K1 * norm)
    return scores


def _assemble(selected: list[Chunk], chunks: list[Chunk]) -> str:
    """Join the kept chunks, marking every gap where material was left out."""
    if not selected:
        return ""
    parts: list[str] = []
    previous: int | None = None
    for chunk in selected:
        gap = chunk.order != (0 if previous is None else previous + 1)
        if gap:
            parts.append("[…]")  # elision, stated rather than hidden
        parts.append(chunk.rendered)
        previous = chunk.order
    if selected[-1].order != len(chunks) - 1:
        parts.append("[…]")
    return "\n\n".join(parts)
