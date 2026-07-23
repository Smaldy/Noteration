"""Schemas for folders, sub-groups, membership and loose files."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field

from backend.schemas.library import DocumentSummaryOut


class FolderGroupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    folder_id: int
    name: str
    tint: str
    order_index: int


class FolderOut(BaseModel):
    """A folder as listed in the Library grid.

    ``item_count``/``child_count`` are transient attributes set by
    ``services.folders.list_folders``, not mapped columns — they let the grid
    pick the empty-folder treatment without fetching contents.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    parent_id: int | None
    subject_id: int | None
    tint: str
    # True on the one folder per subject that auto-mirrors it and receives
    # newly generated notes.
    is_main: bool = False
    bookmarked: bool = False
    order_index: int
    created_at: datetime
    item_count: int = 0
    child_count: int = 0
    # First few document ids, for the Library tray preview. Ids rather than
    # summaries: the client already holds the document list.
    preview_ids: list[int] = []


class FolderFileOut(BaseModel):
    """A loose file, serialized straight from the ORM row.

    ``url`` is computed rather than stored or passed in, so the route shape
    lives in exactly one place instead of being rebuilt by every caller that
    returns a file.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    folder_id: int
    group_id: int | None
    kind: str  # "pdf" | "image"
    filename: str
    content_type: str
    generated_document_id: int | None
    order_index: int

    @computed_field  # type: ignore[prop-decorator]
    @property
    def url(self) -> str:
        return f"/api/folders/files/{self.id}/raw"


class FolderContentsOut(BaseModel):
    """One opened folder: its groups, documents, loose files and children.

    ``document_groups`` maps document id → group id (or null when ungrouped).
    It is kept alongside ``documents`` rather than nested inside each summary
    so ``DocumentSummaryOut`` stays identical to the one the Library list
    returns and the frontend can reuse one card component.
    """

    folder: FolderOut
    groups: list[FolderGroupOut]
    documents: list[DocumentSummaryOut]
    document_groups: dict[int, int | None]
    # document id → starred in *this* folder. A note can be starred here and
    # not in another folder that also references it.
    document_bookmarks: dict[int, bool]
    files: list[FolderFileOut]
    children: list[FolderOut]


class FolderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    parent_id: int | None = None
    subject_id: int | None = None
    # A named tint or a custom "#rrggbb".
    tint: str | None = None
    is_main: bool | None = None


class FolderUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    tint: str | None = None
    subject_id: int | None = None
    parent_id: int | None = None
    # Explicit clears, since `null` on the fields above means "leave alone".
    clear_subject: bool = False
    clear_parent: bool = False
    # None leaves the flag alone; True claims the subject's main slot (demoting
    # whoever held it), False gives it up.
    is_main: bool | None = None


class FolderGroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    tint: str | None = None


class FolderGroupUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    tint: str | None = None


class FolderDocumentsAdd(BaseModel):
    document_ids: list[int]
    group_id: int | None = None


class FolderDocumentGroupUpdate(BaseModel):
    group_id: int | None = None


class GenerateNotesIn(BaseModel):
    """Which subject the promoted document belongs to.

    Optional: a subject-tagged folder supplies its own, so the client only has
    to ask the user when the folder has no tag.
    """

    subject_id: int | None = None


class GeneratedNotesOut(BaseModel):
    """The new document, so the client can route straight to structure review."""

    document_id: int


class BookmarkUpdate(BaseModel):
    """Toggle a folder bookmark, or a note's bookmark within one folder."""

    bookmarked: bool
