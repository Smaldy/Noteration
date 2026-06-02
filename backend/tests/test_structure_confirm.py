"""Confirm-structure tests (Phase 6c): persist reviewed tree + enqueue topics."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import Chapter, Document, Subject, Topic
from backend.models.enums import (
    DocumentMode,
    DocumentStatus,
    QueueStage,
    QueueState,
    TopicPriority,
)
from backend.models.processing import QueueJob
from backend.schemas.structure import ChapterIn, TopicIn
from backend.services import documents as docsvc


def _seed_document(
    session: Session, *, mode: DocumentMode = DocumentMode.study
) -> Document:
    subject = Subject(name="Physics")
    document = Document(subject=subject, filename="f.pdf", file_hash="h", mode=mode)
    session.add_all([subject, document])
    session.commit()
    return document


def _tree() -> list[ChapterIn]:
    return [
        ChapterIn(
            title="Chapter 1",
            topics=[
                TopicIn(title="Kinematics", priority=TopicPriority.exam_critical),
                TopicIn(title="Appendix", priority=TopicPriority.skip),
            ],
        ),
        ChapterIn(title="Chapter 2", topics=[TopicIn(title="Dynamics")]),
    ]


def test_confirm_creates_tree_and_enqueues_non_skip(session: Session) -> None:
    document = _seed_document(session)

    counts = docsvc.confirm_structure(
        session, document.id, chapters=_tree(), exam_date=date(2026, 6, 15)
    )

    assert counts.chapters_created == 2
    assert counts.topics_created == 3
    assert counts.topics_enqueued == 2  # 'skip' topic excluded

    chapters = session.scalars(
        select(Chapter).where(Chapter.document_id == document.id).order_by(Chapter.order_index)
    ).all()
    assert [c.title for c in chapters] == ["Chapter 1", "Chapter 2"]
    # denormalized subject_id propagated from the document
    assert all(c.subject_id == document.subject_id for c in chapters)

    topics = session.scalars(select(Topic)).all()
    assert len(topics) == 3

    # The skip topic has no queue jobs; the other two do.
    skip_topic = next(t for t in topics if t.title == "Appendix")
    skip_jobs = session.scalars(
        select(QueueJob).where(QueueJob.topic_id == skip_topic.id)
    ).all()
    assert skip_jobs == []
    all_jobs = session.scalars(
        select(QueueJob).where(QueueJob.state == QueueState.pending)
    ).all()
    assert {j.topic_id for j in all_jobs} == {
        t.id for t in topics if t.priority is not TopicPriority.skip
    }


def test_confirm_sets_exam_date_and_processing_status(session: Session) -> None:
    document = _seed_document(session)
    docsvc.confirm_structure(
        session, document.id, chapters=_tree(), exam_date=date(2026, 7, 1)
    )

    refreshed = session.get(Document, document.id)
    assert refreshed.status is DocumentStatus.processing
    subject = session.get(Subject, document.subject_id)
    assert subject.exam_date == date(2026, 7, 1)


def test_confirm_without_exam_date_leaves_subject_unchanged(session: Session) -> None:
    document = _seed_document(session)
    docsvc.confirm_structure(session, document.id, chapters=_tree(), exam_date=None)
    subject = session.get(Subject, document.subject_id)
    assert subject.exam_date is None


def test_reconfirm_is_refused(session: Session) -> None:
    document = _seed_document(session)
    docsvc.confirm_structure(session, document.id, chapters=_tree())
    with pytest.raises(docsvc.AlreadyConfirmedError):
        docsvc.confirm_structure(session, document.id, chapters=_tree())


def test_confirm_unknown_document(session: Session) -> None:
    with pytest.raises(docsvc.DocumentNotFoundError):
        docsvc.confirm_structure(session, 999, chapters=_tree())


def test_study_doc_enqueues_formula_and_generation(session: Session) -> None:
    document = _seed_document(session)  # default study mode
    docsvc.confirm_structure(session, document.id, chapters=_tree())
    # Each non-skip topic gets both the formula and the generation (`notes`) stage.
    kinematics = session.scalars(select(Topic).where(Topic.title == "Kinematics")).one()
    stages = session.scalars(
        select(QueueJob.stage).where(QueueJob.topic_id == kinematics.id)
    ).all()
    assert set(stages) == {QueueStage.formula, QueueStage.notes}


def test_exam_doc_enqueues_generation_only(session: Session) -> None:
    document = _seed_document(session, mode=DocumentMode.exam)
    docsvc.confirm_structure(session, document.id, chapters=_tree())
    # Exam mode skips the formula stage — only the generation (`notes`) stage runs.
    kinematics = session.scalars(select(Topic).where(Topic.title == "Kinematics")).one()
    stages = session.scalars(
        select(QueueJob.stage).where(QueueJob.topic_id == kinematics.id)
    ).all()
    assert stages == [QueueStage.notes]
    # No formula jobs anywhere for this exam document.
    formula_jobs = session.scalars(
        select(QueueJob).where(QueueJob.stage == QueueStage.formula)
    ).all()
    assert formula_jobs == []


def test_all_skip_enqueues_nothing(session: Session) -> None:
    document = _seed_document(session)
    chapters = [
        ChapterIn(
            title="C",
            topics=[TopicIn(title="t", priority=TopicPriority.skip)],
        )
    ]
    counts = docsvc.confirm_structure(session, document.id, chapters=chapters)
    assert counts.topics_created == 1
    assert counts.topics_enqueued == 0
    assert session.scalars(select(QueueJob)).all() == []
