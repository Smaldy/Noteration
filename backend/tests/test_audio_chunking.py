"""Audio chunking + trim tests.

The pure planning/parsing logic is exercised with a *faked* ffmpeg runner (no
binary, deterministic), and one integration test drives the real bundled ffmpeg
on generated tone/silence audio to prove split + trim actually work end to end.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from backend.services.pipeline import audio_chunking as ac


# -- pure planning -----------------------------------------------------------


def test_short_audio_is_a_single_chunk() -> None:
    assert ac.plan_split_points(120.0, []) == []
    assert ac.boundaries_from_cuts(120.0, []) == [(0.0, 120.0)]


def test_splits_at_nearest_silence_midpoint() -> None:
    # One hour, silences near each 10-min mark (offset so we test "nearest").
    silences = [(595.0, 605.0), (1180.0, 1220.0), (1810.0, 1814.0)]
    cuts = ac.plan_split_points(3600.0, silences)
    # First cut snaps to the 595-605 gap midpoint (600), well inside [300, 900].
    assert cuts[0] == pytest.approx(600.0)
    # Cuts strictly increasing and within bounds.
    assert cuts == sorted(cuts)
    spans = ac.boundaries_from_cuts(3600.0, cuts)
    for start, end in spans:
        assert 0.0 < end - start <= ac.MAX_CHUNK_SECONDS + 1e-6


def test_hard_cut_when_no_silence_available() -> None:
    cuts = ac.plan_split_points(3600.0, [])
    # No silences → every cut is a hard max-chunk boundary.
    assert cuts[0] == pytest.approx(ac.MAX_CHUNK_SECONDS)
    spans = ac.boundaries_from_cuts(3600.0, cuts)
    assert all(end - start <= ac.MAX_CHUNK_SECONDS + 1e-6 for start, end in spans)
    assert spans[0][0] == 0.0 and spans[-1][1] == 3600.0


def test_silence_outside_band_is_ignored() -> None:
    # A silence at 100s is < min_chunk (300) from the start, so it can't be used;
    # the first cut falls back to the hard max boundary.
    cuts = ac.plan_split_points(2000.0, [(100.0, 110.0)])
    assert cuts[0] == pytest.approx(ac.MAX_CHUNK_SECONDS)


# -- stderr parsing (faked ffmpeg) -------------------------------------------


def _runner(stderr: str) -> ac.FfmpegRunner:
    def _run(_args: Sequence[str]) -> str:
        return stderr

    return _run


def test_probe_duration_parses_header() -> None:
    stderr = "  Duration: 01:02:03.50, start: 0.000000, bitrate: 128 kb/s\n"
    assert ac.probe_duration("x.mp3", runner=_runner(stderr)) == pytest.approx(3723.5)


def test_probe_duration_none_when_absent() -> None:
    assert ac.probe_duration("x.mp3", runner=_runner("no duration here")) is None


def test_detect_silences_pairs_start_and_end() -> None:
    stderr = (
        "[silencedetect] silence_start: 4.0\n"
        "[silencedetect] silence_end: 7.5 | silence_duration: 3.5\n"
        "[silencedetect] silence_start: 20.1\n"  # open-ended (no end) → dropped
    )
    assert ac.detect_silences("x.mp3", runner=_runner(stderr)) == [(4.0, 7.5)]


def test_plan_chunks_single_when_short(monkeypatch: pytest.MonkeyPatch) -> None:
    plan = ac.plan_chunks("x.mp3", runner=_runner("Duration: 00:05:00.00,"))
    assert plan.chunk_count == 1
    assert plan.spans == [(0.0, 300.0)]


def test_plan_chunks_unknown_duration_falls_back_to_whole() -> None:
    plan = ac.plan_chunks("x.mp3", runner=_runner("no duration"))
    assert plan.spans == [(0.0, 0.0)]  # (0,0) → split_audio reads to EOF


# -- real ffmpeg integration -------------------------------------------------


def _generate_audio(path: Path) -> None:
    """tone(4s) + silence(3s) + tone(4s) = 11s with a clear mid silence."""
    ac._default_runner(
        [
            "-hide_banner",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=4:sample_rate=44100",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=44100:cl=mono:duration=3",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=4:sample_rate=44100",
            "-filter_complex",
            "[0][1][2]concat=n=3:v=0:a=1[out]",
            "-map",
            "[out]",
            str(path),
        ]
    )


def test_real_ffmpeg_probe_detect_trim_split(tmp_path: Path) -> None:
    src = tmp_path / "lecture.wav"
    _generate_audio(src)

    duration = ac.probe_duration(src)
    assert duration is not None and 10.5 <= duration <= 11.5

    silences = ac.detect_silences(src)
    assert any(start < 6.0 < end for start, end in silences)  # the mid gap

    # Trim removes most of the 3s gap → shorter file.
    trimmed = tmp_path / "trimmed.wav"
    ac.trim_silence(src, trimmed)
    trimmed_dur = ac.probe_duration(trimmed)
    assert trimmed_dur is not None and trimmed_dur < duration

    # Force a split with small bounds so the 11s file splits at the silence.
    plan = ac.plan_chunks(src, target=5.0, min_chunk=2.0, max_chunk=8.0)
    assert plan.chunk_count == 2
    chunks = ac.split_audio(src, tmp_path / "chunks", plan.spans, ext=".wav")
    assert len(chunks) == 2
    assert all(p.is_file() and p.stat().st_size > 0 for p in chunks)
