"""SQLAlchemy ORM models, per docs/architecture.md.

Importing this package registers every model on ``Base.metadata`` so Alembic
autogenerate and ``create_all`` see the full schema.
"""

from backend.models.arcade import (
    ArcadePlaySession,
    ArcadeState,
    ArcadeUpgrade,
)
from backend.models.content import (
    MCQ,
    Flashcard,
    Formula,
    Note,
    NoteAttachment,
    SourcePage,
)
from backend.models.duplicator import (
    CalibrationSample,
    DuplicateResult,
    ExerciseSession,
    ExtractedExercise,
)
from backend.models.enums import (
    CalibrationSource,
    DocumentMode,
    DocumentStatus,
    ExerciseSessionStatus,
    ExerciseStatus,
    FormulaState,
    HistoryEventType,
    QueueLaneState,
    QueueStage,
    QueueState,
    ScheduleSource,
    TopicPriority,
    TopicStatus,
)
from backend.models.hierarchy import Chapter, Document, Subject, Topic
from backend.models.processing import HistoryEvent, ProviderState, QueueJob
from backend.models.schedule import ScheduleEntry
from backend.models.settings import Settings

__all__ = [
    "Subject",
    "Document",
    "Chapter",
    "Topic",
    "Note",
    "NoteAttachment",
    "Formula",
    "MCQ",
    "Flashcard",
    "SourcePage",
    "ScheduleEntry",
    "QueueJob",
    "ProviderState",
    "HistoryEvent",
    "Settings",
    "ArcadeState",
    "ArcadeUpgrade",
    "ArcadePlaySession",
    "ExerciseSession",
    "ExtractedExercise",
    "DuplicateResult",
    "CalibrationSample",
    "DocumentStatus",
    "DocumentMode",
    "TopicPriority",
    "TopicStatus",
    "QueueStage",
    "QueueState",
    "QueueLaneState",
    "FormulaState",
    "HistoryEventType",
    "ScheduleSource",
    "ExerciseSessionStatus",
    "ExerciseStatus",
    "CalibrationSource",
]
