"""Audio transcription — turn an uploaded lecture into transcript markdown.

An audio document is stored under ``uploads/<hash>.<ext>`` and sits in
``transcribing`` until this runs: it transcribes the whole file with Gemini 3.1
Flash (one fixed model — no rotation, no Ollama fallback, since Ollama can't hear
audio), writes the transcript markdown next to the audio, and flips the document
to ``uploaded`` so it joins the normal structure-review → queue → notes flow. The
transcript markdown is exactly what the note pipeline later reads, so it's also
what the "export transcript" endpoint returns.

On a rate limit the document goes to ``error`` with a "try again later" detail
(per the product decision: transcription waits rather than falling back), and the
user can re-trigger it. The model call is injected so this is unit-testable
without the network.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import Document
from backend.models.enums import DocumentStatus
from backend.services.pipeline.ingestion import UPLOADS_DIR
from backend.services.providers.base import ProviderLimitError, ProviderUnavailableError
from backend.services.providers.gemini import TRANSCRIBE_MODEL, GeminiProvider

# Audio extensions the upload accepts; mapped to the mime type Gemini expects.
AUDIO_MIME: dict[str, str] = {
    ".mp3": "audio/mp3",
    ".wav": "audio/wav",
    ".m4a": "audio/mp4",
    ".aac": "audio/aac",
    ".ogg": "audio/ogg",
    ".oga": "audio/ogg",
    ".opus": "audio/ogg",
    ".flac": "audio/flac",
    ".aiff": "audio/aiff",
    ".aif": "audio/aiff",
    ".mp4": "audio/mp4",
    ".m4b": "audio/mp4",
    ".webm": "audio/webm",
}

SOURCE_TYPE_AUDIO = "audio"

# Transcript files live beside the audio so they share the upload's hash key.
_TRANSCRIPT_SUFFIX = ".transcript.md"

# A transcriber maps (audio_path, mime_type) → transcript markdown.
TranscriberFn = Callable[[str, str], str]

# Language code → name used in the transcription prompt.
_LANGUAGE_NAMES = {"en": "English", "it": "Italian", "es": "Spanish"}

RATE_LIMITED_DETAIL = (
    "Transcription is rate-limited right now. Please wait and try again later."
)


def is_audio_filename(filename: str) -> bool:
    """True when ``filename``'s extension is an accepted audio format."""
    return Path(filename).suffix.lower() in AUDIO_MIME


def audio_mime_for(filename: str) -> str:
    """The Gemini mime type for an audio filename (defaults to audio/mp3)."""
    return AUDIO_MIME.get(Path(filename).suffix.lower(), "audio/mp3")


def build_transcription_prompt(language: str) -> str:
    """Prompt Gemini to transcribe a lecture into clean, segmented markdown."""
    lang = _LANGUAGE_NAMES.get(language, "English")
    return (
        "You are transcribing an audio recording of a university lecture. Produce a "
        "faithful, readable transcript of everything said, as clean Markdown.\n\n"
        f"- Write the transcript in {lang}.\n"
        "- Segment the lecture by subject: start a new `## ` heading each time the "
        "speaker moves to a distinct topic, with a short descriptive title.\n"
        "- Keep the actual content (definitions, explanations, examples, formulas); "
        "drop filler, false starts, and off-topic asides.\n"
        "- Render any equations in LaTeX using $...$ or $$...$$.\n"
        "- Output only the Markdown transcript — no preamble, no commentary."
    )


def audio_path_for(document: Document, uploads_dir: str | Path = UPLOADS_DIR) -> Path:
    """Where an audio document's uploaded file lives: uploads/<hash><ext>."""
    suffix = Path(document.filename).suffix.lower()
    return Path(uploads_dir) / f"{document.file_hash}{suffix}"


def transcript_path_for(
    document: Document, uploads_dir: str | Path = UPLOADS_DIR
) -> Path:
    """Where an audio document's transcript markdown lives."""
    return Path(uploads_dir) / f"{document.file_hash}{_TRANSCRIPT_SUFFIX}"


def transcribe_pending_document(
    session: Session,
    *,
    transcriber: TranscriberFn,
    uploads_dir: str | Path = UPLOADS_DIR,
) -> int | None:
    """Transcribe the oldest ``transcribing`` audio document, if any.

    Returns the document id it acted on (success or error), or ``None`` when there
    is nothing to do. The model call is the injected ``transcriber`` so the
    persistence/status logic is testable without the network.
    """
    document = session.scalars(
        select(Document)
        .where(
            Document.status == DocumentStatus.transcribing,
            Document.source_type == SOURCE_TYPE_AUDIO,
        )
        .order_by(Document.uploaded_at, Document.id)
    ).first()
    if document is None:
        return None

    audio_path = audio_path_for(document, uploads_dir)
    if not audio_path.is_file():
        document.status = DocumentStatus.error
        document.status_detail = "Uploaded audio file is missing."
        session.commit()
        return document.id

    try:
        markdown = transcriber(str(audio_path), audio_mime_for(document.filename))
    except ProviderLimitError:
        document.status = DocumentStatus.error
        document.status_detail = RATE_LIMITED_DETAIL
        session.commit()
        return document.id
    except ProviderUnavailableError as exc:
        document.status = DocumentStatus.error
        document.status_detail = f"Transcription failed: {exc}"
        session.commit()
        return document.id

    if not markdown or not markdown.strip():
        document.status = DocumentStatus.error
        document.status_detail = "Transcription returned no text."
        session.commit()
        return document.id

    transcript_path = transcript_path_for(document, uploads_dir)
    transcript_path.parent.mkdir(parents=True, exist_ok=True)
    transcript_path.write_text(markdown, encoding="utf-8")
    document.markdown_path = str(transcript_path)
    document.status = DocumentStatus.uploaded
    document.status_detail = None
    session.commit()
    return document.id


def make_gemini_transcriber(api_key: str, language: str) -> TranscriberFn:
    """A transcriber that calls Gemini 3.1 Flash with the lecture prompt."""
    provider = GeminiProvider(api_key, models=[TRANSCRIBE_MODEL])
    prompt = build_transcription_prompt(language)

    def _transcribe(audio_path: str, mime_type: str) -> str:
        result = provider.transcribe_audio(
            audio_path, mime_type=mime_type, prompt=prompt
        )
        return result.text

    return _transcribe
