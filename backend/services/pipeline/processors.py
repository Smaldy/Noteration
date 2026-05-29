"""Stage dispatcher — routes a QueueJob to the right stage processor.

The queue's ``run_batch`` takes one ``StageProcessor``; this builds a dispatcher
that selects formula / notes / assessment by ``job.stage``, all sharing one
provider ``Waterfall``. Optional ``source_loader`` / ``cropper`` injectables let
tests drive the pipeline without real markdown files or PyMuPDF.
"""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session

from backend.models.enums import QueueStage
from backend.models.processing import QueueJob
from backend.services.pipeline.formula import RegionCropper, make_formula_processor
from backend.services.pipeline.generation import (
    SourceLoader,
    make_assessment_processor,
    make_notes_processor,
)
from backend.services.providers.base import ProviderResult
from backend.services.providers.waterfall import Waterfall


def make_pipeline_processor(
    waterfall: Waterfall,
    *,
    source_loader: SourceLoader | None = None,
    cropper: RegionCropper | None = None,
) -> Callable[[QueueJob, Session], ProviderResult]:
    """Build a stage-dispatching ``StageProcessor`` over one waterfall."""
    formula_kwargs: dict = {}
    notes_kwargs: dict = {}
    if source_loader is not None:
        formula_kwargs["source_loader"] = source_loader
        notes_kwargs["source_loader"] = source_loader
    if cropper is not None:
        formula_kwargs["cropper"] = cropper

    processors = {
        QueueStage.formula: make_formula_processor(waterfall, **formula_kwargs),
        QueueStage.notes: make_notes_processor(waterfall, **notes_kwargs),
        QueueStage.assessment: make_assessment_processor(waterfall),
    }

    def process(job: QueueJob, session: Session) -> ProviderResult:
        return processors[job.stage](job, session)

    return process
