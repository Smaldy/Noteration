"""Audio transcription — turn an uploaded lecture into transcript markdown.

An audio document is stored under ``uploads/<hash>.<ext>`` and sits in
``transcribing`` until this runs. A one-hour lecture is ~115k Gemini audio tokens
in a single request — enough to blow the free-tier per-minute budget and, once it
429s, unrecoverable (the whole hour must be redone). So instead of one giant call
this stage:

1. **Trims dead air** and **splits the audio into bounded, silence-aligned chunks**
   (``pipeline/audio_chunking.py``) — done once and cached under
   ``uploads/<hash>.chunks/``.
2. **Transcribes the chunks one at a time, resumably.** Each chunk's transcript is
   written to disk as it completes. On a rate limit the finished chunks are kept,
   the document stays ``transcribing`` (not ``error``), and a short backoff is
   recorded in a progress sidecar so the worker resumes at the first missing chunk
   later instead of re-doing the hour.
3. When every chunk is transcribed, concatenates them into the transcript markdown,
   sets ``markdown_path``, flips the document to ``uploaded`` (joining the normal
   structure-review → queue → notes flow), and cleans up the chunk workspace.

Only a hard provider/processing error (not a rate limit) sends the document to
``error``. The model call (``transcriber``) and the chunk preparer are injected so
the persistence/resume logic is unit-testable without the network or ffmpeg.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import Document
from backend.models.enums import DocumentStatus
from backend.paths import UPLOADS_DIR
from backend.services.pipeline import audio_chunking as ac
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
# Per-document chunk workspace: uploads/<hash>.chunks/ (chunk audio + per-chunk
# transcripts + a progress sidecar). Removed once the transcript is assembled.
_CHUNKS_SUFFIX = ".chunks"
_PROGRESS_NAME = "progress.json"
_TRIMMED_STEM = "_trimmed"  # leading underscore so the chunk glob skips it

# A transcriber maps (audio_path, mime_type) → transcript markdown.
TranscriberFn = Callable[[str, str], str]
# A preparer turns one audio file into ordered chunk files under a work dir.
PreparerFn = Callable[..., list[Path]]

# When a rate limit carries no explicit reset, wait this long before resuming the
# remaining chunks (the per-minute window reopens within a minute; this also keeps
# a daily-budget exhaustion from being hammered while still retrying on its own).
DEFAULT_RETRY_BACKOFF = timedelta(minutes=5)

# Language code → name used in the transcription prompt.
_LANGUAGE_NAMES = {"en": "English", "it": "Italian", "es": "Spanish"}


def _utcnow() -> datetime:
    return datetime.now(UTC)


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
        "- This may be one segment of a longer lecture; do not add an introduction "
        "or conclusion — just transcribe what you hear.\n"
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


def chunks_dir_for(document: Document, uploads_dir: str | Path = UPLOADS_DIR) -> Path:
    """The per-document chunk workspace: uploads/<hash>.chunks/."""
    return Path(uploads_dir) / f"{document.file_hash}{_CHUNKS_SUFFIX}"


# -- chunk preparation -------------------------------------------------------


def default_prepare(
    audio_path: Path, work_dir: Path, *, ext: str, trim: bool = True
) -> list[Path]:
    """Trim dead air, then split the audio into ordered chunk files (real ffmpeg).

    The trim pass shrinks the token count before anything is sent; the split is
    silence-aligned so chunks never cut a word. Returns chunk paths in order. A
    short file simply yields one chunk.
    """
    work_dir.mkdir(parents=True, exist_ok=True)
    source = audio_path
    if trim:
        trimmed = work_dir / f"{_TRIMMED_STEM}{ext}"
        try:
            source = ac.trim_silence(audio_path, trimmed)
        except ac.FfmpegError:
            source = audio_path  # trimming is best-effort; fall back to the original
    plan = ac.plan_chunks(source)
    return ac.split_audio(source, work_dir, plan.spans, ext=ext)


def _existing_chunks(work_dir: Path, ext: str) -> list[Path]:
    """Chunk audio files already on disk, in order (excludes the trimmed temp)."""
    return sorted(work_dir.glob(f"chunk-*{ext}"))


def _load_progress(work_dir: Path) -> dict:
    path = work_dir / _PROGRESS_NAME
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_progress(work_dir: Path, progress: dict) -> None:
    work_dir.mkdir(parents=True, exist_ok=True)
    (work_dir / _PROGRESS_NAME).write_text(
        json.dumps(progress), encoding="utf-8"
    )


# -- the worker step ---------------------------------------------------------


def transcribe_pending_document(
    session: Session,
    *,
    transcriber: TranscriberFn,
    uploads_dir: str | Path = UPLOADS_DIR,
    preparer: PreparerFn = default_prepare,
    clock: Callable[[], datetime] = _utcnow,
) -> int | None:
    """Advance the oldest ``transcribing`` audio document by transcribing its chunks.

    Returns the document id it acted on (success, error, or a resumable pause), or
    ``None`` when there's nothing due. Chunk audio is prepared once and cached; each
    chunk transcript is written as it completes, so a rate limit mid-way keeps the
    finished chunks and the document stays ``transcribing`` for a later resume.
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
        return _fail(session, document, "Uploaded audio file is missing.")

    work_dir = chunks_dir_for(document, uploads_dir)
    progress = _load_progress(work_dir)

    # Honor a recorded backoff: nothing due yet → let the worker idle this tick.
    resume_at = progress.get("resume_at")
    if resume_at is not None and clock() < datetime.fromisoformat(resume_at):
        return None

    ext = audio_path.suffix.lower()
    mime = audio_mime_for(document.filename)

    # 1. Prepare chunks once (trim + split), cached across resumes.
    if not progress.get("prepared"):
        try:
            chunk_paths = preparer(audio_path, work_dir, ext=ext)
        except ac.FfmpegError as exc:
            return _fail(session, document, f"Audio processing failed: {exc}")
        if not chunk_paths:
            return _fail(session, document, "Audio produced no chunks to transcribe.")
        progress = {"prepared": True, "chunk_count": len(chunk_paths)}
        _save_progress(work_dir, progress)
    else:
        chunk_paths = _existing_chunks(work_dir, ext)
        if not chunk_paths:  # workspace lost (e.g. cache wiped) → rebuild next tick
            _save_progress(work_dir, {})
            return None

    total = len(chunk_paths)

    # 2. Transcribe each not-yet-done chunk in order; resume on a rate limit.
    for index, chunk_path in enumerate(chunk_paths):
        md_path = work_dir / f"chunk-{index:03d}.md"
        if md_path.is_file():
            continue
        try:
            text = transcriber(str(chunk_path), mime)
        except ProviderLimitError as exc:
            backoff = exc.reset_at or (clock() + DEFAULT_RETRY_BACKOFF)
            progress["resume_at"] = backoff.isoformat()
            _save_progress(work_dir, progress)
            done = sum(
                1 for i in range(total) if (work_dir / f"chunk-{i:03d}.md").is_file()
            )
            document.status_detail = (
                f"Rate-limited — transcribed {done}/{total} segments so far; "
                "resuming automatically."
            )
            session.commit()  # stays transcribing
            return document.id
        except ProviderUnavailableError as exc:
            return _fail(session, document, f"Transcription failed: {exc}")
        md_path.write_text(text or "", encoding="utf-8")
        progress.pop("resume_at", None)
        _save_progress(work_dir, progress)

    # 3. All chunks transcribed → assemble the transcript.
    parts = [
        (work_dir / f"chunk-{i:03d}.md").read_text(encoding="utf-8").strip()
        for i in range(total)
    ]
    markdown = "\n\n".join(part for part in parts if part).strip()
    if not markdown:
        return _fail(session, document, "Transcription returned no text.")

    transcript_path = transcript_path_for(document, uploads_dir)
    transcript_path.parent.mkdir(parents=True, exist_ok=True)
    transcript_path.write_text(markdown, encoding="utf-8")
    document.markdown_path = str(transcript_path)
    document.status = DocumentStatus.uploaded
    document.status_detail = None
    session.commit()
    shutil.rmtree(work_dir, ignore_errors=True)  # workspace no longer needed
    return document.id


def _fail(session: Session, document: Document, detail: str) -> int:
    """Mark the document errored with ``detail`` and commit; return its id."""
    document.status = DocumentStatus.error
    document.status_detail = detail
    session.commit()
    return document.id


def make_gemini_transcriber(api_key: str, language: str) -> TranscriberFn:
    """A transcriber that calls Gemini Flash with the lecture prompt, per chunk."""
    provider = GeminiProvider(api_key, models=[TRANSCRIBE_MODEL])
    prompt = build_transcription_prompt(language)

    def _transcribe(audio_path: str, mime_type: str) -> str:
        result = provider.transcribe_audio(
            audio_path, mime_type=mime_type, prompt=prompt
        )
        return result.text

    return _transcribe
