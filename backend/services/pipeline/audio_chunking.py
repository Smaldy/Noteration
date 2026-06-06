"""Audio chunking + silence trimming — make hour-long lectures transcribable.

Gemini tokenizes audio at ~32 tokens/second, so a one-hour lecture is ~115k
input tokens in a single request — enough to blow the free-tier per-minute token
budget on its own, and unrecoverable once it 429s (the whole hour must be redone).
This module is the fix: it (1) strips long dead air to shrink the token count and
(2) splits the remaining audio into bounded chunks **at silence boundaries** so no
word is cut, letting the transcriber process them one at a time, paced and
resumable (see services/transcription.py).

ffmpeg is provided by the bundled ``imageio-ffmpeg`` wheel (a static binary, no
system install, fully offline). The pure planning logic (``plan_split_points``)
is dependency-free and unit-tested; the thin ffmpeg-driving helpers take an
injectable ``runner`` so they can be faked in tests, with one real integration
test exercising the actual binary on ffmpeg-generated audio.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

# A chunk targets ~10 minutes (~19k Gemini audio tokens), clamped to a [min, max]
# band so a chunk is never tiny or large enough to risk the per-minute budget.
TARGET_CHUNK_SECONDS = 600.0
MIN_CHUNK_SECONDS = 300.0
MAX_CHUNK_SECONDS = 900.0

# silencedetect tuning: a gap quieter than this for at least this long is a
# candidate split point (and, for trimming, dead air to drop).
SILENCE_NOISE_DB = -30.0
SILENCE_MIN_SECONDS = 1.5

# A ffmpeg runner takes the args *after* the executable and returns its stderr
# (ffmpeg writes progress/metadata there). Injectable for tests.
FfmpegRunner = Callable[[Sequence[str]], str]

_DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")
_SILENCE_START_RE = re.compile(r"silence_start:\s*(-?[\d.]+)")
_SILENCE_END_RE = re.compile(r"silence_end:\s*([\d.]+)")


class FfmpegError(RuntimeError):
    """ffmpeg exited non-zero on a command whose success we depend on."""


def ffmpeg_exe() -> str:
    """Path to the bundled static ffmpeg binary (lazy import of imageio-ffmpeg)."""
    import imageio_ffmpeg  # lazy: keeps the import optional for non-audio paths

    return imageio_ffmpeg.get_ffmpeg_exe()


def _default_runner(args: Sequence[str]) -> str:
    """Run ffmpeg with ``args``; return stderr. Raises on a non-zero exit."""
    proc = subprocess.run(  # noqa: S603 - args are app-built, exe is the bundled binary
        [ffmpeg_exe(), *args],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise FfmpegError(proc.stderr.strip()[-500:] or "ffmpeg failed")
    return proc.stderr


def _probe_runner(args: Sequence[str]) -> str:
    """Like ``_default_runner`` but tolerates ffmpeg's non-zero 'no output' exit.

    ``ffmpeg -i FILE`` (no output file) prints the container metadata — including
    ``Duration:`` — then exits 1. We only want the stderr text, so don't raise.
    """
    proc = subprocess.run(  # noqa: S603 - args are app-built, exe is the bundled binary
        [ffmpeg_exe(), *args],
        capture_output=True,
        text=True,
    )
    return proc.stderr


# -- duration + silence probing ----------------------------------------------


def probe_duration(path: str | Path, *, runner: FfmpegRunner | None = None) -> float | None:
    """Total audio duration in seconds, or ``None`` if ffmpeg doesn't report it."""
    run = runner or _probe_runner
    stderr = run(["-hide_banner", "-i", str(path)])
    match = _DURATION_RE.search(stderr)
    if match is None:
        return None
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def detect_silences(
    path: str | Path,
    *,
    noise_db: float = SILENCE_NOISE_DB,
    min_seconds: float = SILENCE_MIN_SECONDS,
    runner: FfmpegRunner | None = None,
) -> list[tuple[float, float]]:
    """Silence intervals ``(start, end)`` in seconds, via ffmpeg ``silencedetect``.

    An open-ended trailing silence (a ``silence_start`` with no matching
    ``silence_end`` before EOF) is dropped — it's not a usable interior cut point.
    """
    run = runner or _probe_runner
    stderr = run(
        [
            "-hide_banner",
            "-i",
            str(path),
            "-af",
            f"silencedetect=noise={noise_db}dB:d={min_seconds}",
            "-f",
            "null",
            "-",
        ]
    )
    intervals: list[tuple[float, float]] = []
    pending_start: float | None = None
    for line in stderr.splitlines():
        start = _SILENCE_START_RE.search(line)
        if start is not None:
            pending_start = float(start.group(1))
            continue
        end = _SILENCE_END_RE.search(line)
        if end is not None and pending_start is not None:
            intervals.append((pending_start, float(end.group(1))))
            pending_start = None
    return intervals


# -- pure split planning (unit-tested, no ffmpeg) ----------------------------


def plan_split_points(
    duration: float,
    silences: Sequence[tuple[float, float]],
    *,
    target: float = TARGET_CHUNK_SECONDS,
    min_chunk: float = MIN_CHUNK_SECONDS,
    max_chunk: float = MAX_CHUNK_SECONDS,
) -> list[float]:
    """Interior cut times (seconds) splitting ``duration`` into bounded chunks.

    Each cut is placed at the silence midpoint nearest the running target that
    falls within ``[pos+min_chunk, pos+max_chunk]``; if no silence qualifies, a
    hard cut at ``pos+max_chunk`` bounds the chunk. Returns the strictly
    increasing interior boundaries (excludes 0 and ``duration``); an audio shorter
    than ``max_chunk`` yields ``[]`` (a single chunk).
    """
    if duration <= max_chunk:
        return []
    midpoints = sorted((s + e) / 2 for s, e in silences if e > s)
    cuts: list[float] = []
    pos = 0.0
    while duration - pos > max_chunk:
        ideal = pos + target
        lo, hi = pos + min_chunk, pos + max_chunk
        candidates = [m for m in midpoints if lo <= m <= hi and m > pos]
        cut = min(candidates, key=lambda m: abs(m - ideal)) if candidates else hi
        cuts.append(round(cut, 3))
        pos = cut
    return cuts


def boundaries_from_cuts(duration: float, cuts: Sequence[float]) -> list[tuple[float, float]]:
    """Turn interior cut times into ``(start, end)`` segment spans covering [0, duration]."""
    edges = [0.0, *cuts, duration]
    return [(edges[i], edges[i + 1]) for i in range(len(edges) - 1)]


# -- ffmpeg-driving operations -----------------------------------------------


def trim_silence(
    src: str | Path,
    dst: str | Path,
    *,
    noise_db: float = SILENCE_NOISE_DB,
    min_seconds: float = SILENCE_MIN_SECONDS,
    runner: FfmpegRunner | None = None,
) -> Path:
    """Write ``src`` to ``dst`` with long silences removed (``silenceremove``).

    Removes every silent stretch (``stop_periods=-1``) quieter than ``noise_db``
    lasting at least ``min_seconds`` — dead air between sentences is kept short but
    not eliminated (the filter leaves up to ``min_seconds`` so speech stays
    natural). Re-encodes (stream copy can't apply a filter); the output keeps the
    source container/extension.
    """
    run = runner or _default_runner
    dst_path = Path(dst)
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    run(
        [
            "-hide_banner",
            "-y",
            "-i",
            str(src),
            "-vn",  # audio only — sources may be video containers (.mp4/.webm/.m4b)
            "-af",
            (
                f"silenceremove=stop_periods=-1:stop_duration={min_seconds}"
                f":stop_threshold={noise_db}dB"
            ),
            str(dst_path),
        ]
    )
    return dst_path


def split_audio(
    src: str | Path,
    out_dir: str | Path,
    spans: Sequence[tuple[float, float]],
    *,
    ext: str,
    runner: FfmpegRunner | None = None,
) -> list[Path]:
    """Cut ``src`` into one file per ``(start, end)`` span under ``out_dir``.

    Files are named ``chunk-000<ext>``, ``chunk-001<ext>`` … in span order. Uses
    stream copy (fast, lossless); silence-aligned cuts tolerate copy's keyframe
    slop. A single span ``[(0, duration)]`` still produces one chunk file, so the
    caller can treat short and long audio uniformly.
    """
    run = runner or _default_runner
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for index, (start, end) in enumerate(spans):
        chunk_path = out / f"chunk-{index:03d}{ext}"
        args = ["-hide_banner", "-y", "-ss", f"{start:.3f}"]
        # The final span runs to EOF; omit -to so a slightly-short probed duration
        # never truncates the tail.
        if index < len(spans) - 1:
            args += ["-to", f"{end:.3f}"]
        # -vn drops any video stream (mp4/webm containers) so chunks are audio-only;
        # -c copy keeps the audio lossless and the cut fast.
        args += ["-i", str(src), "-vn", "-c", "copy", str(chunk_path)]
        run(args)
        paths.append(chunk_path)
    return paths


@dataclass
class ChunkPlan:
    """The decided segmentation for one audio file (after any trim)."""

    duration: float
    spans: list[tuple[float, float]]

    @property
    def chunk_count(self) -> int:
        return len(self.spans)


def plan_chunks(
    path: str | Path,
    *,
    target: float = TARGET_CHUNK_SECONDS,
    min_chunk: float = MIN_CHUNK_SECONDS,
    max_chunk: float = MAX_CHUNK_SECONDS,
    runner: FfmpegRunner | None = None,
) -> ChunkPlan:
    """Probe ``path`` and decide its silence-aligned segment spans.

    A file whose duration can't be probed falls back to a single span of unknown
    length ``(0, 0)`` meaning "transcribe whole" — handled by ``split_audio``'s
    EOF-tail rule, so we never fail to make progress just because probing failed.
    """
    duration = probe_duration(path, runner=runner)
    if duration is None or duration <= max_chunk:
        # One chunk: (0, duration) when known, else (0, 0) → whole file to EOF.
        return ChunkPlan(duration or 0.0, [(0.0, duration or 0.0)])
    silences = detect_silences(path, runner=runner)
    cuts = plan_split_points(
        duration, silences, target=target, min_chunk=min_chunk, max_chunk=max_chunk
    )
    return ChunkPlan(duration, boundaries_from_cuts(duration, cuts))
