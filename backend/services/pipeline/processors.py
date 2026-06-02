"""Stage dispatcher — routes a QueueJob to the right stage processor.

The queue's ``run_batch`` takes one ``StageProcessor``; this builds a dispatcher
that selects the formula stage (region detection/registration, vision deferred)
or the consolidated generation stage (`notes` — notes + assessment in one call)
by ``job.stage``, sharing one provider ``Waterfall``. Optional ``source_loader`` /
``cropper`` injectables let tests drive the pipeline without real markdown or
PyMuPDF. A retired ``assessment`` job (legacy data) is a no-op.
"""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session

from backend.models.enums import QueueStage
from backend.models.processing import QueueJob
from backend.services.pipeline.formula import RegionLocator, make_formula_processor
from backend.services.pipeline.generation import (
    SourceLoader,
    make_generation_processor,
)
from backend.services.providers.base import ProviderResult
from backend.services.providers.waterfall import Waterfall

# Stamp for a stage that did no model call (e.g. a retired assessment job).
_NO_OP_PROVIDER = "none"


def make_pipeline_processor(
    waterfall: Waterfall,
    *,
    source_loader: SourceLoader | None = None,
    locator: RegionLocator | None = None,
) -> Callable[[QueueJob, Session], ProviderResult]:
    """Build a stage-dispatching ``StageProcessor`` over one waterfall.

    The formula stage makes no model call (region registration only), so it does
    not use the waterfall; the consolidated generation stage does.
    """
    formula_kwargs: dict = {}
    generation_kwargs: dict = {}
    if source_loader is not None:
        formula_kwargs["source_loader"] = source_loader
        generation_kwargs["source_loader"] = source_loader
    if locator is not None:
        formula_kwargs["locator"] = locator

    processors = {
        QueueStage.formula: make_formula_processor(**formula_kwargs),
        QueueStage.notes: make_generation_processor(waterfall, **generation_kwargs),
    }

    def process(job: QueueJob, session: Session) -> ProviderResult:
        handler = processors.get(job.stage)
        if handler is None:  # retired stage (e.g. legacy `assessment` job)
            return ProviderResult(text="", provider=_NO_OP_PROVIDER)
        return handler(job, session)

    return process
