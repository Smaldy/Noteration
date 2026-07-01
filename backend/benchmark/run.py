"""Sequential benchmark runner — Gemini-free vs. Ollama-local.

Runs a fixed set of representative topics through a provider **one at a time**,
with the provider's production inter-request cooldown ACTIVE, and records the
metrics that decide the default bulk provider (docs/architecture.md).

Why sequential + cooldown + >= 40 topics: a short burst hides exactly what
matters for the broke-student / overnight use case — sustained-throughput
degradation and thermal throttling on a 6GB 3060 laptop. So the runner refuses
to report on fewer than ``MIN_TOPICS`` topics (cycling the samples if needed) and
includes the cooldown in every wall-clock figure. The reported throughput is
therefore *sustained overnight behavior, not burst speed* — that caveat rides
along in ``BenchmarkReport.notes`` so a reader can't misread the number.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from backend.benchmark.rubric import count_math_blocks, score_formulas, score_notes
from backend.services.providers.base import (
    Provider,
    ProviderError,
    ProviderLimitError,
    ProviderResult,
)

# Minimum topics for a meaningful sustained run. A shorter sample can't surface
# thermal throttling or quota-window degradation, so we never report on less.
MIN_TOPICS = 40
# Output cap per topic — mirrors the consolidated generation stage so the
# benchmark prompt is representative of production load.
BENCHMARK_MAX_TOKENS = 4096


@dataclass(frozen=True)
class BenchmarkTopic:
    """One representative topic fed to a provider."""

    id: str
    title: str
    source: str
    # Number of math blocks the source contains, for the formula-accuracy proxy.
    expected_math_blocks: int = 0

    @classmethod
    def from_source(cls, id: str, title: str, source: str) -> "BenchmarkTopic":
        return cls(id, title, source, expected_math_blocks=count_math_blocks(source))


@dataclass
class TopicResult:
    topic_id: str
    ok: bool
    wall_seconds: float
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0
    note_score: float = 0.0
    formula_score: float = 0.0
    error: str | None = None


@dataclass
class BenchmarkReport:
    provider: str
    requested_topics: int
    completed_topics: int
    # Topics processed before the provider first hit a quota/rate limit (the
    # "throughput before limit" metric). Equals completed_topics if never limited.
    topics_before_limit: int
    limited: bool
    total_wall_seconds: float
    cooldown_included: bool
    total_cost: float = 0.0
    avg_note_score: float = 0.0
    avg_formula_score: float = 0.0
    results: list[TopicResult] = field(default_factory=list)
    notes: str = ""

    @property
    def topics_per_hour(self) -> float:
        """Sustained throughput (cooldown-inclusive). 0 when nothing completed."""
        if self.total_wall_seconds <= 0 or self.completed_topics == 0:
            return 0.0
        return self.completed_topics / (self.total_wall_seconds / 3600.0)


def default_prompt_builder(topic: BenchmarkTopic) -> str:
    """A representative notes prompt for one topic (kept self-contained)."""
    return (
        "Write dense, exam-useful study notes in Markdown for the topic "
        f"'{topic.title}'. Use ## / ### headings, short paragraphs, and bullet "
        "lists; reserve **bold** for key terms; write any math as LaTeX.\n\n"
        f"Source:\n{topic.source}"
    )


def _cycle_to_minimum(
    topics: Sequence[BenchmarkTopic], minimum: int
) -> list[BenchmarkTopic]:
    """Repeat the sample topics (in order) until there are at least ``minimum``.

    Cycling re-runs the same topics so a sustained run can be measured even from a
    small representative sample; each repeat gets a distinct id suffix so results
    stay individually attributable.
    """
    if not topics:
        return []
    out: list[BenchmarkTopic] = []
    pass_no = 0
    while len(out) < minimum:
        for topic in topics:
            if pass_no == 0:
                out.append(topic)
            else:
                out.append(
                    BenchmarkTopic(
                        id=f"{topic.id}#r{pass_no}",
                        title=topic.title,
                        source=topic.source,
                        expected_math_blocks=topic.expected_math_blocks,
                    )
                )
            if len(out) >= minimum:
                return out
        pass_no += 1
    return out


def run_benchmark(
    provider: Provider,
    topics: Sequence[BenchmarkTopic],
    *,
    min_topics: int = MIN_TOPICS,
    max_tokens: int = BENCHMARK_MAX_TOKENS,
    prompt_builder: Callable[[BenchmarkTopic], str] = default_prompt_builder,
    time_fn: Callable[[], float] = time.monotonic,
) -> BenchmarkReport:
    """Run ``topics`` through ``provider`` sequentially and score the output.

    The provider's own inter-request cooldown (if any) runs inside ``generate``,
    so every ``wall_seconds`` — and the aggregate throughput — already includes
    it. Stops on the first provider quota/rate limit (recording how many topics
    completed before it); other per-topic errors are recorded and the run
    continues.
    """
    run_topics = _cycle_to_minimum(topics, min_topics)
    cooldown_included = getattr(provider, "cooldown_seconds", 0) > 0

    results: list[TopicResult] = []
    limited = False
    topics_before_limit = 0
    total_wall = 0.0

    for topic in run_topics:
        t0 = time_fn()
        try:
            result: ProviderResult = provider.generate(
                prompt_builder(topic), max_tokens=max_tokens
            )
        except ProviderLimitError as exc:
            # Quota/rate wall — this is the "throughput before limit" boundary.
            limited = True
            results.append(
                TopicResult(
                    topic_id=topic.id,
                    ok=False,
                    wall_seconds=time_fn() - t0,
                    error=f"limit: {exc}",
                )
            )
            break
        except ProviderError as exc:
            results.append(
                TopicResult(
                    topic_id=topic.id,
                    ok=False,
                    wall_seconds=time_fn() - t0,
                    error=str(exc),
                )
            )
            continue
        wall = time_fn() - t0
        total_wall += wall
        topics_before_limit += 1
        results.append(
            TopicResult(
                topic_id=topic.id,
                ok=True,
                wall_seconds=wall,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                cost=result.cost,
                note_score=score_notes(result.text),
                formula_score=score_formulas(result.text, topic.expected_math_blocks),
            )
        )

    completed = [r for r in results if r.ok]
    n_ok = len(completed)
    report = BenchmarkReport(
        provider=provider.name,
        requested_topics=len(run_topics),
        completed_topics=n_ok,
        topics_before_limit=topics_before_limit,
        limited=limited,
        total_wall_seconds=total_wall,
        cooldown_included=cooldown_included,
        total_cost=round(sum(r.cost for r in completed), 6),
        avg_note_score=round(sum(r.note_score for r in completed) / n_ok, 3) if n_ok else 0.0,
        avg_formula_score=(
            round(sum(r.formula_score for r in completed) / n_ok, 3) if n_ok else 0.0
        ),
        results=results,
    )
    report.notes = _summarize(report)
    return report


def _summarize(report: BenchmarkReport) -> str:
    cooldown = "INCLUDES inter-request cooldown" if report.cooldown_included else "no cooldown"
    limit = (
        f"; hit a quota/rate limit after {report.topics_before_limit} topic(s)"
        if report.limited
        else ""
    )
    return (
        f"Throughput {report.topics_per_hour:.1f} topics/hour ({cooldown}); "
        "reflects SUSTAINED overnight behavior, not burst speed"
        f"{limit}."
    )


def format_report(report: BenchmarkReport) -> str:
    """A human-readable block for the CLI."""
    return "\n".join(
        [
            f"=== {report.provider} ===",
            f"  completed:        {report.completed_topics}/{report.requested_topics}",
            f"  topics/hour:      {report.topics_per_hour:.1f}  (sustained, cooldown-inclusive)",
            f"  before limit:     {report.topics_before_limit}",
            f"  total wall:       {report.total_wall_seconds:.1f}s",
            f"  total cost:       ${report.total_cost:.4f}",
            f"  note quality:     {report.avg_note_score:.3f}",
            f"  formula accuracy: {report.avg_formula_score:.3f}",
            f"  note: {report.notes}",
        ]
    )


def _load_samples() -> list[BenchmarkTopic]:
    """Load the representative sample topics shipped under ``samples/``."""
    import json
    from pathlib import Path

    path = Path(__file__).parent / "samples" / "topics.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return [
        BenchmarkTopic.from_source(item["id"], item["title"], item["source"])
        for item in data
    ]


def main() -> None:  # pragma: no cover - CLI entry, exercised manually with keys
    """Run the benchmark against any configured candidate providers.

    Reads keys/model from the environment so it never touches the app DB:
    ``GEMINI_API_KEY`` enables the Gemini-free run; ``OLLAMA_MODEL`` enables the
    Ollama-local run (cooldown active). At least one must be set.
    """
    import os

    from backend.services.providers.gemini import GeminiProvider
    from backend.services.providers.ollama import OllamaProvider

    topics = _load_samples()
    providers: list[Provider] = []
    if os.environ.get("GEMINI_API_KEY"):
        providers.append(GeminiProvider(os.environ["GEMINI_API_KEY"]))
    if os.environ.get("OLLAMA_MODEL"):
        # Cooldown stays at its production default — the benchmark must measure
        # the same behavior the queue will see overnight.
        providers.append(OllamaProvider(model=os.environ["OLLAMA_MODEL"]))

    if not providers:
        raise SystemExit("Set GEMINI_API_KEY and/or OLLAMA_MODEL to run the benchmark.")

    for provider in providers:
        report = run_benchmark(provider, topics)
        print(format_report(report))


if __name__ == "__main__":  # pragma: no cover
    main()
