"""End-to-end pipeline test: confirm → queue → consolidated generation.

Drives a confirmed document's topics through the real queue with the stage
dispatcher. The provider returns one combined JSON object (notes + assessment)
per generation call. Proves the formula→generation ordering and atomic commits
produce studiable material per topic in a single generation call.
"""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy.orm import Session

from backend.models import MCQ, Document, Flashcard, Note, Subject
from backend.models.enums import (
    DocumentMode,
    QueueLaneState,
    QueueStage,
    QueueState,
    TopicPriority,
)
from backend.models.processing import QueueJob
from backend.schemas.structure import ChapterIn, TopicIn
from backend.services import documents as docsvc
from backend.services.pipeline.processors import make_pipeline_processor
from backend.services.providers.base import BudgetProbe, Provider, ProviderResult
from backend.services.providers.waterfall import Waterfall
from backend.services.queue import QueueService

_GENERATION = {
    "notes_md": "# Kinematics\n\nVelocity is dx/dt.",
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
    """Returns the combined notes+assessment JSON object for every generate call."""

    name = "smart_free"
    supports_vision = True

    def generate(
        self, prompt: str, *, max_tokens: int, response_schema=None
    ) -> ProviderResult:
        return ProviderResult(text=json.dumps(_GENERATION), provider=self.name)

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
                queue_state=QueueLaneState.running,
                topics=[TopicIn(title="Kinematics", priority=TopicPriority.exam_critical)],
            )
        ],
    )
    return document


def test_full_topic_pipeline_produces_studiable_material(
    session: Session, tmp_path: Path
) -> None:
    _seed_confirmed_document(session, tmp_path)
    topic_id = session.query(QueueJob).first().topic_id

    queue = QueueService(session)
    processor = make_pipeline_processor(Waterfall([_SmartProvider()]))
    processed = queue.run_batch(processor, max_jobs=20)

    # 2 stage jobs for the one non-skip topic: formula (no math → no-op) and the
    # consolidated generation stage (notes + assessment in one call).
    assert processed == 2
    assert all(j.state is QueueState.done for j in session.query(QueueJob).all())

    note = session.query(Note).filter_by(topic_id=topic_id).one()
    assert "Velocity is dx/dt" in note.content_md
    assert session.query(MCQ).filter_by(topic_id=topic_id).count() == 1
    assert session.query(Flashcard).filter_by(topic_id=topic_id).count() == 1


def test_exam_doc_pipeline_produces_assessment_only(
    session: Session, tmp_path: Path
) -> None:
    md = tmp_path / "doc.md"
    md.write_text("# Kinematics\n\nVelocity is dx/dt.\n", encoding="utf-8")
    subject = Subject(name="Physics")
    document = Document(
        subject=subject,
        filename="f.pdf",
        file_hash="h",
        markdown_path=str(md),
        mode=DocumentMode.exam,
    )
    session.add_all([subject, document])
    session.commit()
    docsvc.confirm_structure(
        session,
        document.id,
        chapters=[
            ChapterIn(
                title="Mechanics",
                queue_state=QueueLaneState.running,
                topics=[TopicIn(title="Kinematics", priority=TopicPriority.exam_critical)],
            )
        ],
    )
    topic_id = session.query(QueueJob).first().topic_id

    queue = QueueService(session)
    processor = make_pipeline_processor(Waterfall([_SmartProvider()]))
    processed = queue.run_batch(processor, max_jobs=20)

    # Exam mode enqueues only the generation stage — no formula stage.
    assert processed == 1
    assert session.query(QueueJob).filter_by(stage=QueueStage.formula).count() == 0
    assert all(j.state is QueueState.done for j in session.query(QueueJob).all())

    # Assessment material, but no notes.
    assert session.query(Note).filter_by(topic_id=topic_id).count() == 0
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
    assert remaining == 1  # only the generation stage remained (2 stages total)
    assert session.query(Note).count() == 1
    assert session.query(MCQ).count() == 1
