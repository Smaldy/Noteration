"""Folders — the Library's organizing layer over the content hierarchy.

The hierarchy in ``hierarchy.py`` (Subject → Document → Chapter → Topic) says
what content *is*; folders say where the user wants to *see* it. The two are
deliberately independent, which is why a folder never owns a Document.

Membership of a folder is the union of two sources:

* **Auto** — a folder with ``subject_id`` set mirrors that subject's documents.
  Nothing is written for this: it's a query, so uploading a new PDF to the
  subject makes it appear in the folder immediately, and removing the tag
  removes them all without leaving orphan rows behind.
* **Manual** — a ``FolderItem`` row places one specific document in the folder.
  This is what "copy into another folder" creates, so the same document can be
  referenced from several folders without being duplicated on disk or in the
  hierarchy.

``FolderFile`` is the third kind of content and the only one a folder *owns*:
a PDF or image dropped straight into the folder, inert until the user asks for
notes. It carries ``folder_id`` directly and cascade-deletes with the folder,
unlike documents, which outlive any folder that references them.

Nesting is capped at two levels (a root folder and its children). SQLite can't
express "my parent must have no parent", so ``services/folders.py`` enforces it
on every create and move.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.database import Base
from backend.db.types import UTCDateTime
from backend.models.hierarchy import utcnow

if TYPE_CHECKING:
    from backend.models.hierarchy import Document, Subject

# Mirrors TINT_NAMES in src/lib/tints.ts — the two lists must stay in step, or
# the UI falls back to the neutral tint for a color the backend accepted.
TINT_NAMES = (
    "rose",
    "amber",
    "mint",
    "sky",
    "lilac",
    "peach",
    "sage",
    "slate",
)
DEFAULT_TINT = "slate"


class Folder(Base):
    __tablename__ = "folders"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    # Null for a root folder. Cascade so deleting a root takes its children
    # (and, through them, their groups and owned files) with it.
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("folders.id", ondelete="CASCADE"), default=None
    )
    # The "subject tag". SET NULL rather than CASCADE: deleting a subject should
    # not destroy a folder the user built, which may still hold loose files and
    # manually placed documents. It degrades to an ordinary manual folder.
    subject_id: Mapped[int | None] = mapped_column(
        ForeignKey("subjects.id", ondelete="SET NULL"), default=None
    )
    # Custom tints are stored here as a raw "#rrggbb"; the named ones from
    # TINT_NAMES are stored by name. The client tells them apart by the leading
    # "#", so no second column is needed.
    tint: Mapped[str] = mapped_column(default=DEFAULT_TINT, server_default=DEFAULT_TINT)
    # The subject's *main* folder. Only the main folder auto-mirrors its
    # subject's documents, and newly generated notes land there. Without this,
    # two folders tagged to one subject each showed every note in it, so the
    # same note appeared twice across the Library with no way to say where it
    # belonged. At most one folder per subject may carry the flag; the service
    # enforces that on write, since SQLite can't express a partial unique index
    # portably here.
    is_main: Mapped[bool] = mapped_column(default=False, server_default="0")
    # Library-level bookmark. Folders are what the Library's bookmark filter
    # narrows to; individual notes are bookmarked per folder on FolderItem.
    bookmarked: Mapped[bool] = mapped_column(default=False, server_default="0")
    order_index: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    subject: Mapped[Subject | None] = relationship("Subject")
    children: Mapped[list[Folder]] = relationship(
        back_populates="parent", cascade="all, delete-orphan"
    )
    parent: Mapped[Folder | None] = relationship(
        back_populates="children", remote_side=[id]
    )
    groups: Mapped[list[FolderGroup]] = relationship(
        back_populates="folder", cascade="all, delete-orphan"
    )
    items: Mapped[list[FolderItem]] = relationship(
        back_populates="folder", cascade="all, delete-orphan"
    )
    files: Mapped[list[FolderFile]] = relationship(
        back_populates="folder", cascade="all, delete-orphan"
    )


class FolderGroup(Base):
    """A named, colored band within one folder (e.g. "Exam 1", "Theory").

    Groups are optional: an item with ``group_id`` null sits in the folder's
    default ungrouped area. Deleting a group leaves its contents in the folder
    rather than deleting them, so the FKs pointing here are SET NULL.
    """

    __tablename__ = "folder_groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    folder_id: Mapped[int] = mapped_column(ForeignKey("folders.id", ondelete="CASCADE"))
    name: Mapped[str]
    tint: Mapped[str] = mapped_column(default=DEFAULT_TINT, server_default=DEFAULT_TINT)
    order_index: Mapped[int] = mapped_column(default=0)

    folder: Mapped[Folder] = relationship(back_populates="groups")


class FolderItem(Base):
    """A manual placement of one document into one folder.

    Absent for documents that appear via their folder's ``subject_id`` tag —
    those are computed, never stored. The unique constraint keeps a document
    from being added to the same folder twice; placing it in a *different*
    folder is a second row, which is what the copy action does.
    """

    __tablename__ = "folder_items"
    __table_args__ = (
        UniqueConstraint("folder_id", "document_id", name="uq_folder_item_document"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    folder_id: Mapped[int] = mapped_column(ForeignKey("folders.id", ondelete="CASCADE"))
    # The document keeps living in its subject if the folder goes away, but a
    # deleted document must not leave a dangling placement behind.
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE")
    )
    group_id: Mapped[int | None] = mapped_column(
        ForeignKey("folder_groups.id", ondelete="SET NULL"), default=None
    )
    # Bookmarked *within this folder*: the same document can be starred in one
    # folder and not another, because the flag lives on the placement rather
    # than on the document. Bookmarking a subject-tagged member creates its
    # FolderItem, exactly as filing one into a group does.
    bookmarked: Mapped[bool] = mapped_column(default=False, server_default="0")
    order_index: Mapped[int] = mapped_column(default=0)

    folder: Mapped[Folder] = relationship(back_populates="items")
    document: Mapped[Document] = relationship("Document")


class FolderFile(Base):
    """A PDF or image dropped straight into a folder, inert by default.

    Bytes live in the shared content-addressed store under
    ``cache/attachments/<hash><ext>`` (see services/attachments.persist_bytes),
    so the same file in two folders costs one copy on disk.

    ``generated_document_id`` records the Document produced if the user later
    runs "generate notes" on this file. It makes that action idempotent and
    keeps the file from being listed twice: once the link exists, the folder
    shows the generated document rather than the raw file again.
    """

    __tablename__ = "folder_files"

    id: Mapped[int] = mapped_column(primary_key=True)
    folder_id: Mapped[int] = mapped_column(ForeignKey("folders.id", ondelete="CASCADE"))
    group_id: Mapped[int | None] = mapped_column(
        ForeignKey("folder_groups.id", ondelete="SET NULL"), default=None
    )
    kind: Mapped[str]  # "pdf" | "image"
    filename: Mapped[str]  # original upload name (carries the extension)
    content_type: Mapped[str]
    file_hash: Mapped[str]  # cache/attachments/<hash><ext>
    # SET NULL so deleting the generated document offers the file for
    # generation again instead of orphaning the row.
    generated_document_id: Mapped[int | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), default=None
    )
    order_index: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    folder: Mapped[Folder] = relationship(back_populates="files")
    generated_document: Mapped[Document | None] = relationship("Document")
