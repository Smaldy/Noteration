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
  only "finishes by morning". On a dedicated GPU its pool additionally
  includes a share of system RAM: Ollama transparently offloads weights that
  don't fit VRAM, and nobody waits for the overnight model, so a bigger model
  running partly from RAM beats a smaller one that fits — speed is estimated
  with the offload-blended bandwidth. **Fast model** is speed-bound: best
  quality clearing ~20 tok/s, hard floor 10 tok/s (accepted with a
  sluggishness warning), and it never offloads (interactive latency dies
  with it).
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
    blended_bandwidth_gbps,
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
from backend.services.local_ai.hardware import GraphicsClass, HardwareProfile

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

# Quality-role offload pool: on a dedicated GPU the overnight model may spill
# this share of system RAM (the rest stays for the OS and the app). Only the
# quality role — the fast model must sit fully in VRAM to stay responsive.
OFFLOAD_RAM_FRACTION = 0.5

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
    offloaded: bool = False  # part of the weights would live in system RAM


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


def quality_pool_bytes(profile: HardwareProfile) -> int:
    """The quality role's memory pool: VRAM plus the RAM offload share.

    Integrated/CPU profiles already size against system RAM, so only a
    dedicated GPU gains anything from offloading.
    """
    if profile.graphics_class is GraphicsClass.dedicated and profile.ram_bytes:
        return profile.usable_memory_bytes + int(
            profile.ram_bytes * OFFLOAD_RAM_FRACTION
        )
    return profile.usable_memory_bytes


def enumerate_combos(
    profile: HardwareProfile,
    models: tuple[CatalogModel, ...] = MODELS,
    *,
    pool_bytes: int | None = None,
) -> list[Combo]:
    """Every (model × quant) that fits the pool, scored together.

    ``pool_bytes`` defaults to the strict resident pool. A larger pool (the
    quality role's offload pool) admits combos whose weights partly spill to
    system RAM; their speed is estimated with the offload-blended bandwidth.
    """
    pool = pool_bytes if pool_bytes is not None else profile.usable_memory_bytes
    bandwidth_gbps, _ = bandwidth_for_profile(profile)
    kv = kv_bytes_per_token
    combos: list[Combo] = []
    for model in models:
        for quant in quants_for(model):
            context = fit_context(model, quant, pool)
            if context is None:
                continue
            size = model.size_bytes(quant)
            needed = size + context * kv(model.params_b) + RUNTIME_OVERHEAD_BYTES
            offload_frac = max(0.0, needed - profile.usable_memory_bytes) / size
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
                    size_bytes=size,
                    est_tok_s=estimate_tok_per_sec(
                        model.bytes_read_per_token(quant),
                        blended_bandwidth_gbps(bandwidth_gbps, offload_frac),
                    ),
                    score=score,
                    offloaded=offload_frac > 0.0,
                )
            )
    return combos


def _best(combos: list[Combo]) -> Combo | None:
    # Score first; ties go to the larger context, then the faster combo.
    return max(combos, key=lambda c: (c.score, c.context, c.est_tok_s), default=None)


def select_models(
    profile: HardwareProfile, models: tuple[CatalogModel, ...] = MODELS
) -> SelectionResult:
    fast_combos = enumerate_combos(profile, models)
    quality_combos = enumerate_combos(
        profile, models, pool_bytes=quality_pool_bytes(profile)
    )
    messages: list[str] = []
    if not quality_combos:  # superset of fast_combos — nothing fits at all
        messages.append(
            "This machine does not have enough free memory to run even the "
            "smallest local model. Local AI setup is not possible on this hardware."
        )
        return SelectionResult(None, None, converged=False, weak_machine=True, messages=messages)

    # Quality role: memory-bound (offload pool), no responsiveness floor.
    quality = _best(
        [c for c in quality_combos if c.est_tok_s >= OVERNIGHT_FLOOR_TOK_S]
    )
    if quality is None:  # nothing finishes by morning; take the least-bad combo
        quality = _best(quality_combos)

    # Fast role: speed-bound, strictly resident. Try the responsive target,
    # then the hard floor.
    decent = [c for c in fast_combos if c.model.params_b >= DECENT_PARAMS_B]
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
        fast = _best(
            [c for c in fast_combos if c.est_tok_s >= FAST_HARD_FLOOR_TOK_S]
        )
        if fast is None and fast_combos:
            fast = max(fast_combos, key=lambda c: (c.est_tok_s, c.score))
        if fast is None:  # nothing fits VRAM strictly; run the quality pick
            fast = quality
        quality = fast
        messages.append(
            "This hardware can only run a small local model, so generation "
            "will be slow and notes will be simpler. Everything still works "
            "offline. If you add a cloud API key later (for example Gemini), "
            "you will get better results when you are online."
        )
    elif quality.offloaded:
        messages.append(
            "The quality model is larger than the graphics memory, so part of "
            "it will run from system memory. That makes it slow, which is fine "
            "for overnight generation."
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
