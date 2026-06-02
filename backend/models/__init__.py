"""SQLAlchemy ORM models, per docs/data-model.md.

Importing this package registers every model on ``Base.metadata`` so Alembic
autogenerate and ``create_all`` see the full schema.
"""

from backend.models.content import MCQ, Flashcard, Formula, Note, SourcePage
from backend.models.enums import (
    DocumentMode,
    DocumentStatus,
    FormulaState,
    QueueStage,
    QueueState,
    ScheduleSource,
    TopicPriority,
    TopicStatus,
)
from backend.models.hierarchy import Chapter, Document, Subject, Topic
from backend.models.processing import ProviderState, QueueJob
from backend.models.schedule import ScheduleEntry
from backend.models.settings import Settings

__all__ = [
    "Subject",
    "Document",
    "Chapter",
    "Topic",
    "Note",
    "Formula",
    "MCQ",
    "Flashcard",
    "SourcePage",
    "ScheduleEntry",
    "QueueJob",
    "ProviderState",
    "Settings",
    "DocumentStatus",
    "DocumentMode",
    "TopicPriority",
    "TopicStatus",
    "QueueStage",
    "QueueState",
    "FormulaState",
    "ScheduleSource",
]
