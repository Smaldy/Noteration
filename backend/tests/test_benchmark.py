"""Benchmark-harness tests (Wave A).

The harness is an offline script, but its sustained-run discipline is the whole
point (docs/architecture.md), so we lock it in: >= 40 sequential topics, the
provider's real cooldown active in the timing, throughput labelled as
sustained/cooldown-inclusive, and a clean stop at the first quota limit.
"""

from __future__ import annotations

from types import SimpleNamespace

from backend.benchmark.rubric import score_formulas, score_notes
from backend.benchmark.run import (
    MIN_TOPICS,
    BenchmarkTopic,
    _load_samples,
    run_benchmark,
)
from backend.services.providers.base import (
    BudgetProbe,
    Provider,
    ProviderLimitError,
    ProviderResult,
)
from backend.services.providers.ollama import OllamaProvider


class _LimitAfter(Provider):
    """A quota-style provider that 429s after ``n`` successful calls.

    Models a free tier (e.g. Gemini) which maps a 429 to ``ProviderLimitError`` —
    the signal the benchmark uses to measure "throughput before limit". (Ollama is
    local and never raises a limit error, so it can't drive this path.)
    """

    name = "fake_free"

    def __init__(self, n: int) -> None:
        self.n = n
        self.calls = 0

    def generate(self, prompt, *, max_tokens, response_schema=None) -> ProviderResult:
        self.calls += 1
        if self.calls > self.n:
            raise ProviderLimitError("429 quota exhausted")
        return ProviderResult(text=NOTE, provider=self.name, input_tokens=100, output_tokens=200)

    def transcribe_image(self, image, *, max_tokens=1024) -> ProviderResult:  # pragma: no cover
        raise NotImplementedError

    def budget_probe(self) -> BudgetProbe:  # pragma: no cover
        return BudgetProbe(True, 1000, "rpm", None, False)

NOTE = "## Heading\n\nA clear paragraph.\n\n- point one\n- point two\n\n$E = mc^2$"


def _ollama():
    """A fake-client Ollama provider that always succeeds (cooldown active)."""
    state = {"n": 0}

    def generate(**_kwargs):
        state["n"] += 1
        return {"response": NOTE, "prompt_eval_count": 100, "eval_count": 200}

    provider = OllamaProvider(
        model="llama3",
        client=SimpleNamespace(generate=generate),
        cooldown_seconds=3.0,
        sleep=lambda _s: None,  # don't actually sleep in the test
    )
    return provider, state


def test_benchmark_runs_at_least_40_topics_sequentially() -> None:
    provider, state = _ollama()
    topics = [BenchmarkTopic.from_source(f"t{i}", f"Topic {i}", NOTE) for i in range(5)]
    # A monotonic fake clock so wall-time is deterministic (1s per call boundary).
    ticks = iter(range(10_000))
    report = run_benchmark(provider, topics, time_fn=lambda: next(ticks))

    assert state["n"] >= MIN_TOPICS  # cycled the 5 samples up to the minimum
    assert report.completed_topics >= MIN_TOPICS
    assert report.requested_topics >= MIN_TOPICS


def test_benchmark_throughput_is_cooldown_inclusive_and_labelled() -> None:
    provider, _ = _ollama()
    topics = _load_samples()
    ticks = iter(range(0, 100_000, 1))
    report = run_benchmark(provider, topics, time_fn=lambda: next(ticks))

    assert report.cooldown_included is True
    assert "cooldown" in report.notes.lower()
    assert "sustained" in report.notes.lower()
    assert report.topics_per_hour > 0


def test_benchmark_stops_at_first_limit_and_records_throughput_before_limit() -> None:
    provider = _LimitAfter(10)
    topics = [BenchmarkTopic.from_source(f"t{i}", f"Topic {i}", NOTE) for i in range(5)]
    ticks = iter(range(10_000))
    report = run_benchmark(provider, topics, time_fn=lambda: next(ticks))

    assert report.limited is True
    assert report.topics_before_limit == 10
    assert report.completed_topics == 10  # stopped at the wall, didn't push past it


def test_benchmark_scores_real_provider_output() -> None:
    provider, _ = _ollama()
    topics = [BenchmarkTopic.from_source("t", "Topic", NOTE)]
    ticks = iter(range(10_000))
    report = run_benchmark(provider, topics, time_fn=lambda: next(ticks))
    # NOTE has a heading, bullets, and a formula, so both scores should be high.
    assert report.avg_note_score > 0.6
    assert report.avg_formula_score == 1.0


def test_rubric_penalizes_bold_wall_and_empty() -> None:
    assert score_notes("") == 0.0
    bold_wall = "\n".join(f"**bolded line {i} of text**" for i in range(20))
    structured = NOTE
    assert score_notes(structured) > score_notes(bold_wall)


def test_rubric_formula_recall() -> None:
    assert score_formulas("no math here", expected_math_blocks=2) == 0.0
    assert score_formulas("$a$ and $b$", expected_math_blocks=2) == 1.0
    assert score_formulas("anything", expected_math_blocks=0) == 1.0
