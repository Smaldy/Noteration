"""Note-quality + formula-accuracy scoring for the benchmark.

Deterministic, offline heuristics — no model judges another model. These are
rough rubric scores (0.0-1.0) good enough to compare two providers on the same
topics; they are NOT a substitute for a human spot-check of the winner. The
make-or-break metric for engineering material is formula accuracy, so it is
scored separately from prose quality.
"""

from __future__ import annotations

import re

# LaTeX delimiters the generation prompt is told to use for math.
_MATH_PATTERNS = (
    re.compile(r"\$\$.+?\$\$", re.DOTALL),
    re.compile(r"\$[^$\n]+?\$"),
    re.compile(r"\\\[.+?\\\]", re.DOTALL),
    re.compile(r"\\\(.+?\\\)", re.DOTALL),
)
_HEADING = re.compile(r"^#{2,6}\s+\S", re.MULTILINE)
_BULLET = re.compile(r"^\s*[-*]\s+\S", re.MULTILINE)
_BOLD = re.compile(r"\*\*[^*]+\*\*")


def count_math_blocks(text: str) -> int:
    """How many LaTeX math spans the text contains (any delimiter style)."""
    return sum(len(p.findall(text)) for p in _MATH_PATTERNS)


def score_notes(text: str) -> float:
    """Heuristic note-quality score in [0, 1].

    Rewards structure (headings + bullets) and adequate length; penalizes the
    "bold wall of text" failure mode (a note where almost every line is bolded
    carries no real structure). Empty notes score 0.
    """
    text = (text or "").strip()
    if not text:
        return 0.0

    score = 0.0
    if _HEADING.search(text):
        score += 0.35
    if _BULLET.search(text):
        score += 0.25
    # Length: reward a substantive note, capped so verbosity alone can't win.
    words = len(text.split())
    score += min(words / 250.0, 1.0) * 0.25

    # Penalize a bold wall: bolded characters dominating the body.
    bold_chars = sum(len(m) for m in _BOLD.findall(text))
    if bold_chars / max(len(text), 1) < 0.4:
        score += 0.15

    return round(min(score, 1.0), 3)


def score_formulas(text: str, expected_math_blocks: int) -> float:
    """Formula-accuracy proxy in [0, 1] vs. the expected number of math blocks.

    With no expected math the score is a perfect 1.0 (nothing to get wrong).
    Otherwise it's the fraction of expected blocks the output reproduced, capped
    at 1.0 — a coarse recall signal, not a transcription-correctness judge.
    """
    if expected_math_blocks <= 0:
        return 1.0
    produced = count_math_blocks(text)
    return round(min(produced / expected_math_blocks, 1.0), 3)
