"""Stages 2, 4, and 7 — pick the two models (quality + fast) for a machine.

Pure functions over a ``HardwareProfile`` and the bundled catalog: no I/O, no
network, fully unit-testable against fixture profiles (Task 2). The install
stage consumes the ``SelectionResult``; Stage 5's confirm screen renders it.

Selection rules (spec):
- Score **(model × quant)** combinations together, never model-then-quant.
  Each model contributes Q4_K_M (the floor) plus one higher quant.
- **Context-shrink lever**: a combo that misses at the default context is
  retried at smaller contexts before being discarded; shrinking context costs
  less quality than shrinking the model. The ladder never drops below what a
  generation call actually needs (~2k prompt + 2k output).
- **Quality model** is memory-bound: best effective quality that fits, floor
  only "finishes by morning". **Fast model** is speed-bound: best quality
  clearing ~20 tok/s, hard floor 10 tok/s (accepted with a sluggishness
  warning).
- **Weak machines stay local** (Stage 7): when nothing decent clears even the
  hard floor, the scheme collapses to the single best small model, honestly
  flagged — never a cloud handoff.

The two roles frequently converge on strong dedicated GPUs (whatever fills
VRAM is also fast); ``converged`` marks that so the installer pulls once and
the UI shows one model with both roles.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.services.local_ai.bandwidth import (
    bandwidth_for_profile,
    estimate_tok_per_sec,
)
from backend.services.local_ai.catalog import (
    MODELS,
    Q4_K_M,
    Q5_K_M,
    Q6_K,
    CatalogModel,
    kv_bytes_per_token,
)
from backend.services.local_ai.hardware import HardwareProfile

# Context ladder (tokens). 8192 is the comfortable default; 4096 is the floor
# because a generation call runs ~2k prompt + ~2k output (services/pipeline/
# generation.py) and must fit in one window.
CONTEXT_STEPS = (8192, 4096)

# Fixed runtime cost on top of weights + kv cache (CUDA/Metal context, compute
# buffers, scratch). Conservative round figure.
RUNTIME_OVERHEAD_BYTES = 768 * 1024**2

# Effective-quality adjustment per quant (relative ranks, same scale as the
# catalog's ``quality``): Q4 loses noticeably more than Q5/Q6. This is what
# lets a larger model at Q4 beat a smaller one at Q6 — or not — numerically.
QUANT_QUALITY_ADJ = {Q4_K_M: -5, Q5_K_M: -2, Q6_K: -1}
# Each context step below the default costs a little effective quality, so an
# unshrunk combo wins ties (shrinking is a lever, not a free action).
CONTEXT_SHRINK_PENALTY = 1

# Stage 4 floors (tok/s).
FAST_TARGET_TOK_S = 20.0  # feels responsive
FAST_HARD_FLOOR_TOK_S = 10.0  # usable but sluggish
OVERNIGHT_FLOOR_TOK_S = 1.0  # only "finishes by morning"

# A "decent" interactive model (Stage 7's bar) is 3B-class or better.
DECENT_PARAMS_B = 3.0

# Per model: the Q4 floor plus ONE higher quant (spec). Small models take Q6
# (the extra bytes are cheap and the quality gain matters most at small
# sizes); big models take Q5 (Q6 on a 30B rarely fits anywhere Q5 doesn't
# already saturate).
_Q6_MAX_PARAMS_B = 9.0


def quants_for(model: CatalogModel) -> tuple[str, str]:
    return (Q4_K_M, Q6_K if model.params_b <= _Q6_MAX_PARAMS_B else Q5_K_M)


@dataclass(frozen=True)
class Combo:
    """One (model × quant) candidate that fits, at its largest fitting context."""

    model: CatalogModel
    quant: str
    context: int
    size_bytes: float
    est_tok_s: float
    score: float  # effective quality: catalog quality + quant/context adjustments


@dataclass(frozen=True)
class ModelChoice:
    tag: str
    display: str
    quant: str
    context: int
    download_bytes: int
    est_tok_s: float

    @staticmethod
    def from_combo(combo: Combo) -> ModelChoice:
        return ModelChoice(
            tag=combo.model.tag,
            display=combo.model.display,
            quant=combo.quant,
            context=combo.context,
            download_bytes=int(combo.size_bytes),
            est_tok_s=round(combo.est_tok_s, 1),
        )


@dataclass(frozen=True)
class SelectionResult:
    """What Stage 5 shows and Stage 6 installs.

    ``converged`` means both roles picked the same combo (install once).
    ``weak_machine`` means even the hard speed floor failed for a decent
    model: the single-small-model scheme (Stage 7) is in effect and the UI
    must tell the user honestly. ``messages`` carry those honest notes.
    """

    quality: ModelChoice | None
    fast: ModelChoice | None
    converged: bool
    weak_machine: bool
    messages: list[str] = field(default_factory=list)

    @property
    def total_download_bytes(self) -> int:
        unique = {
            (c.tag, c.quant): c.download_bytes
            for c in (self.quality, self.fast)
            if c is not None
        }
        return sum(unique.values())


def fit_context(model: CatalogModel, quant: str, usable_bytes: int) -> int | None:
    """Largest context step at which weights + kv + overhead fit, else None.

    This is the Stage 2 context-shrink lever: walk the ladder down before
    giving up on the (model × quant) combo entirely.
    """
    size = model.size_bytes(quant)
    kv_per_token = kv_bytes_per_token(model.params_b)
    for context in CONTEXT_STEPS:
        needed = size + context * kv_per_token + RUNTIME_OVERHEAD_BYTES
        if needed <= usable_bytes:
            return context
    return None


def enumerate_combos(
    profile: HardwareProfile, models: tuple[CatalogModel, ...] = MODELS
) -> list[Combo]:
    """Every (model × quant) that fits usable memory, scored together."""
    bandwidth_gbps, _ = bandwidth_for_profile(profile)
    combos: list[Combo] = []
    for model in models:
        for quant in quants_for(model):
            context = fit_context(model, quant, profile.usable_memory_bytes)
            if context is None:
                continue
            shrink_steps = CONTEXT_STEPS.index(context)
            score = (
                model.quality
                + QUANT_QUALITY_ADJ[quant]
                - CONTEXT_SHRINK_PENALTY * shrink_steps
            )
            combos.append(
                Combo(
                    model=model,
                    quant=quant,
                    context=context,
                    size_bytes=model.size_bytes(quant),
                    est_tok_s=estimate_tok_per_sec(
                        model.bytes_read_per_token(quant), bandwidth_gbps
                    ),
                    score=score,
                )
            )
    return combos


def _best(combos: list[Combo]) -> Combo | None:
    # Score first; ties go to the larger context, then the faster combo.
    return max(combos, key=lambda c: (c.score, c.context, c.est_tok_s), default=None)


def select_models(
    profile: HardwareProfile, models: tuple[CatalogModel, ...] = MODELS
) -> SelectionResult:
    combos = enumerate_combos(profile, models)
    messages: list[str] = []
    if not combos:
        messages.append(
            "This machine does not have enough free memory to run even the "
            "smallest local model. Local AI setup is not possible on this hardware."
        )
        return SelectionResult(None, None, converged=False, weak_machine=True, messages=messages)

    # Quality role: memory-bound, no responsiveness floor.
    quality = _best([c for c in combos if c.est_tok_s >= OVERNIGHT_FLOOR_TOK_S])
    if quality is None:  # nothing finishes by morning; take the least-bad combo
        quality = _best(combos)

    # Fast role: speed-bound. Try the responsive target, then the hard floor.
    decent = [c for c in combos if c.model.params_b >= DECENT_PARAMS_B]
    fast = _best([c for c in decent if c.est_tok_s >= FAST_TARGET_TOK_S])
    weak_machine = False
    if fast is None:
        fast = _best([c for c in decent if c.est_tok_s >= FAST_HARD_FLOOR_TOK_S])
        if fast is not None:
            messages.append(
                "Interactive generation on this hardware is estimated at about "
                f"{fast.est_tok_s:.0f} tokens per second. It will work, but it "
                "will feel slow."
            )
    if fast is None:
        # Stage 7: nothing decent clears even the hard floor. Collapse to the
        # single best small model that still moves, stay local, and say so.
        weak_machine = True
        fast = _best([c for c in combos if c.est_tok_s >= FAST_HARD_FLOOR_TOK_S])
        if fast is None:
            fast = max(combos, key=lambda c: (c.est_tok_s, c.score))
        quality = fast
        messages.append(
            "This hardware can only run a small local model, so generation "
            "will be slow and notes will be simpler. Everything still works "
            "offline. If you add a cloud API key later (for example Gemini), "
            "you will get better results when you are online."
        )

    converged = (quality.model.tag, quality.quant, quality.context) == (
        fast.model.tag,
        fast.quant,
        fast.context,
    )
    return SelectionResult(
        quality=ModelChoice.from_combo(quality),
        fast=ModelChoice.from_combo(fast),
        converged=converged,
        weak_machine=weak_machine,
        messages=messages,
    )
