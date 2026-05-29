"""End-to-end pipeline test (Phase 7e): confirm → queue → notes + assessment.

Drives a confirmed document's topics through the real queue with the stage
dispatcher, using one provider that answers notes vs. assessment prompts
appropriately. Proves the formula→notes→assessment ordering and atomic commits
produce studiable material per topic.
"""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy.orm import Session

from backend.models import Document, Flashcard, MCQ, Note, Subject
from backend.models.enums import QueueState, TopicPriority
from backend.models.processing import QueueJob
from backend.schemas.structure import ChapterIn, TopicIn
from backend.services import documents as docsvc
from backend.services.pipeline.processors import make_pipeline_processor
from backend.services.queue import QueueService
from backend.services.providers.base import BudgetProbe, Provider, ProviderResult
from backend.services.providers.waterfall import Waterfall

_ASSESSMENT = {
    "mcqs": [
        {
            "question": "What is velocity?",
            "options": ["dx/dt", "ma", "mgh"],
            "correct_index": 0,
            "explanation": "rate of position change",
        }
    ],
    "flashcards": [{"front": "acceleration?", "back": "dv/dt"}],
}


class _SmartProvider(Provider):
    """Returns assessment JSON for the assessment prompt, notes prose otherwise."""

    name = "smart_free"
    supports_vision = True

    def generate(self, prompt: str, *, max_tokens: int) -> ProviderResult:
        if "Respond with ONLY a JSON" in prompt:
            return ProviderResult(text=json.dumps(_ASSESSMENT), provider=self.name)
        return ProviderResult(text="# Kinematics\n\nVelocity is dx/dt.", provider=self.name)

    def transcribe_image(self, image: bytes, *, max_tokens: int = 1024) -> ProviderResult:
        return ProviderResult(text="v = dx/dt", provider=self.name)

    def budget_probe(self) -> BudgetProbe:
        return BudgetProbe(True, 100, "none", None, True)


def _seed_confirmed_document(session: Session, tmp_path: Path) -> Document:
    md = tmp_path / "doc.md"
    md.write_text("# Kinematics\n\nVelocity is dx/dt.\n", encoding="utf-8")
    subject = Subject(name="Physics")
    document = Document(
        subject=subject, filename="f.pdf", file_hash="h", markdown_path=str(md)
    )
    session.add_all([subject, document])
    session.commit()
    docsvc.confirm_structure(
        session,
        document.id,
        chapters=[
            ChapterIn(
                title="Mechanics",
                topics=[TopicIn(title="Kinematics", priority=TopicPriority.exam_critical)],
            )
        ],
    )
    return document


def test_full_topic_pipeline_produces_studiable_material(
    session: Session, tmp_path: Path
) -> None:
    document = _seed_confirmed_document(session, tmp_path)
    topic_id = session.query(QueueJob).first().topic_id

    queue = QueueService(session)
    processor = make_pipeline_processor(Waterfall([_SmartProvider()]))
    processed = queue.run_batch(processor, max_jobs=20)

    # 3 stage jobs for the one non-skip topic: formula (no math → no-op), notes,
    # assessment.
    assert processed == 3
    assert all(j.state is QueueState.done for j in session.query(QueueJob).all())

    note = session.query(Note).filter_by(topic_id=topic_id).one()
    assert "Velocity is dx/dt" in note.content_md
    assert session.query(MCQ).filter_by(topic_id=topic_id).count() == 1
    assert session.query(Flashcard).filter_by(topic_id=topic_id).count() == 1


def test_pipeline_resumes_after_restart(session: Session, tmp_path: Path) -> None:
    # Process only the first job, then simulate a fresh run that finishes the rest.
    _seed_confirmed_document(session, tmp_path)
    queue = QueueService(session)
    processor = make_pipeline_processor(Waterfall([_SmartProvider()]))

    first = queue.run_batch(processor, max_jobs=1)
    assert first == 1

    # New service instance (fresh "session") recovers and completes the topic.
    queue2 = QueueService(session)
    queue2.recover_orphaned_jobs()
    remaining = queue2.run_batch(processor, max_jobs=20)
    assert remaining == 2
    assert session.query(Note).count() == 1
    assert session.query(MCQ).count() == 1
