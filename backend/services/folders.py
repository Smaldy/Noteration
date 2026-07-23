"""Folder service — the Library's organizing layer.

Owns folder CRUD, sub-groups, membership and loose files. See
``models/folders.py`` for why a folder never owns a Document and what the two
membership sources are.

The one rule that can't live in the schema is nesting depth: SQLite has no way
to say "my parent must itself have no parent", so every create and move calls
``_assert_can_parent``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from backend.models import Document, Folder, FolderFile, FolderGroup, FolderItem
from backend.models.enums import DocumentMode
from backend.models.folders import DEFAULT_TINT, TINT_NAMES
from backend.paths import UPLOADS_DIR
from backend.services import documents as documentsvc
from backend.services.attachments import persist_bytes, release_file, store_path
from backend.services.documents import DocumentSummary, IngestFn
from backend.services.pipeline.ingestion import ingest

# PDFs run larger than the note attachments that share this store, so this cap
# is set above MAX_ATTACHMENT_BYTES rather than reusing it.
MAX_FOLDER_FILE_BYTES = 100 * 1024 * 1024

# How many document ids a folder carries for its tray preview in the Library.
PREVIEW_LIMIT = 3


class FolderNotFoundError(LookupError):
    """Referenced folder does not exist."""


class FolderGroupNotFoundError(LookupError):
    """Referenced group does not exist, or belongs to another folder."""


class FolderFileNotFoundError(LookupError):
    """Referenced folder file does not exist."""


class FolderDepthError(ValueError):
    """The move/create would nest folders more than two levels deep."""


class UnsupportedFolderFileError(ValueError):
    """The file isn't a PDF or image, is empty, or is too large."""


class MissingSubjectError(ValueError):
    """Generating notes needs a subject, and neither the caller nor the folder
    supplied one."""


@dataclass
class FolderContents:
    """One folder, fully resolved for rendering.

    ``documents`` merges both membership sources; ``document_groups`` maps a
    document id to the group it sits in, which is only ever set by a manual
    ``FolderItem`` (auto members start ungrouped until the user files them).
    """

    folder: Folder
    groups: list[FolderGroup]
    documents: list[DocumentSummary]
    document_groups: dict[int, int | None] = field(default_factory=dict)
    # Per-folder bookmarks, keyed by document id. Absent/false for auto members
    # that have never been starred here.
    document_bookmarks: dict[int, bool] = field(default_factory=dict)
    files: list[FolderFile] = field(default_factory=list)
    children: list[Folder] = field(default_factory=list)


_HEX_TINT = re.compile(r"^#[0-9a-fA-F]{6}$")


def _normalize_tint(tint: str | None) -> str:
    """Accept a named tint or a custom ``#rrggbb``.

    Anything else falls back to the neutral rather than being rejected, so a
    client on an older tint list can't fail a whole create.
    """
    if tint in TINT_NAMES:
        return tint  # type: ignore[return-value]
    if tint and _HEX_TINT.match(tint):
        return tint.lower()
    return DEFAULT_TINT


def _claim_main(session: Session, folder: Folder) -> None:
    """Make ``folder`` its subject's main folder, demoting any current holder.

    Called whenever a folder is explicitly marked main, and implicitly when a
    subject gains its first tagged folder — so the common one-folder-per-subject
    case keeps working without the user ever seeing the setting.
    """
    if folder.subject_id is None:
        folder.is_main = False
        return
    session.execute(
        update(Folder)
        .where(
            Folder.subject_id == folder.subject_id,
            Folder.id != folder.id,
            Folder.is_main.is_(True),
        )
        .values(is_main=False)
    )
    folder.is_main = True


def _subject_has_main(
    session: Session, subject_id: int, *, excluding: int | None = None
) -> bool:
    query = (
        select(func.count())
        .select_from(Folder)
        .where(Folder.subject_id == subject_id, Folder.is_main.is_(True))
    )
    if excluding is not None:
        query = query.where(Folder.id != excluding)
    return bool(session.scalar(query))


def _get_folder(session: Session, folder_id: int) -> Folder:
    folder = session.get(Folder, folder_id)
    if folder is None:
        raise FolderNotFoundError(folder_id)
    return folder


def _assert_can_parent(
    session: Session, parent_id: int | None, *, moving: int | None = None
) -> None:
    """Enforce the two-level cap (and, for moves, reject self-parenting)."""
    if parent_id is None:
        return
    parent = _get_folder(session, parent_id)
    if parent.parent_id is not None:
        raise FolderDepthError("folders nest at most two levels deep")
    if moving is not None:
        if parent.id == moving:
            raise FolderDepthError("a folder cannot be its own parent")
        # Moving a folder that has children under another folder would push
        # those children to depth three.
        has_children = session.scalar(
            select(func.count()).select_from(Folder).where(Folder.parent_id == moving)
        )
        if has_children:
            raise FolderDepthError("a folder with children cannot become a child")


def _next_order(session: Session, model: type, **filters) -> int:
    """Append position for a new row within its scope.

    Scope columns are nullable (a root folder has ``parent_id`` NULL), so the
    None case must use ``IS NULL``: ``column == None`` renders as ``= NULL``,
    which is never true in SQL and would silently scope every root folder to an
    empty set, handing them all ``order_index`` 0.
    """
    query = select(func.coalesce(func.max(model.order_index), -1))
    for column, value in filters.items():
        attr = getattr(model, column)
        query = query.where(attr.is_(None) if value is None else attr == value)
    # Compared against None rather than `or -1`: the first row in a scope has
    # order_index 0, which is falsy and would otherwise be read as "no rows",
    # pinning the second row to 0 as well.
    current = session.scalar(query)
    return (-1 if current is None else int(current)) + 1


def _decorate(session: Session, folders: list[Folder]) -> list[Folder]:
    """Attach the transient ``item_count``/``child_count``/``preview_ids``.

    Every endpoint that returns a Folder must run it through here. These are not
    mapped columns, so a bare ORM row serializes them as 0/0/[] — which the
    Library reads as an empty folder and renders with the dashed empty-state
    treatment. Returning an undecorated folder from create/update is what made a
    folder look like it had been emptied the moment you recolored it.
    """
    if not folders:
        return folders

    # Promoted files are counted as their document instead (see get_contents),
    # so excluding them here keeps the tray count matching what the folder shows.
    files = dict(
        session.execute(
            select(FolderFile.folder_id, func.count(FolderFile.id))
            .where(FolderFile.generated_document_id.is_(None))
            .group_by(FolderFile.folder_id)
        ).all()
    )
    children = dict(
        session.execute(
            select(Folder.parent_id, func.count(Folder.id))
            .where(Folder.parent_id.is_not(None))
            .group_by(Folder.parent_id)
        ).all()
    )
    # Auto membership, keyed by subject: ids (for the tray preview) rather than
    # a count, since the count falls out of the same rows.
    docs_by_subject: dict[int, list[int]] = {}
    for doc_id, subject_id in session.execute(
        select(Document.id, Document.subject_id)
        .where(Document.mode == DocumentMode.study)
        .order_by(Document.order_index, Document.id)
    ).all():
        docs_by_subject.setdefault(subject_id, []).append(doc_id)

    docs_by_folder: dict[int, list[int]] = {}
    for folder_id, doc_id in session.execute(
        select(FolderItem.folder_id, FolderItem.document_id).order_by(
            FolderItem.order_index, FolderItem.id
        )
    ).all():
        docs_by_folder.setdefault(folder_id, []).append(doc_id)

    for folder in folders:
        # Only the subject's main folder auto-mirrors it; other folders tagged
        # to the same subject show just what was placed in them by hand.
        auto = (
            docs_by_subject.get(folder.subject_id, [])
            if folder.subject_id and folder.is_main
            else []
        )
        placed = docs_by_folder.get(folder.id, [])
        # Same union rule as get_contents: a document that is both tagged in and
        # manually placed must be counted once.
        merged = list(dict.fromkeys([*auto, *placed]))
        folder.item_count = len(merged) + files.get(folder.id, 0)  # type: ignore[attr-defined]
        folder.child_count = children.get(folder.id, 0)  # type: ignore[attr-defined]
        # Ids, not full summaries: the Library already holds every document, so
        # the client resolves these locally instead of re-sending the payload.
        folder.preview_ids = merged[:PREVIEW_LIMIT]  # type: ignore[attr-defined]
    return folders


def list_folders(session: Session) -> list[Folder]:
    """All folders in display order, roots first then children."""
    return _decorate(
        session,
        list(
            session.execute(
                select(Folder).order_by(Folder.order_index, Folder.id)
            ).scalars()
        ),
    )


def get_contents(session: Session, folder_id: int) -> FolderContents:
    """Resolve one folder's groups, documents, loose files and child folders."""
    folder = _get_folder(session, folder_id)

    groups = list(
        session.execute(
            select(FolderGroup)
            .where(FolderGroup.folder_id == folder_id)
            .order_by(FolderGroup.order_index, FolderGroup.id)
        ).scalars()
    )

    # Auto members first, then manual placements overlaid on top — a document
    # that is both (a subject member the user filed into a group) keeps the
    # group from its FolderItem.
    placement: dict[int, int | None] = {}
    order: dict[int, int] = {}
    if folder.subject_id is not None and folder.is_main:
        auto_ids = session.execute(
            select(Document.id).where(
                Document.subject_id == folder.subject_id,
                Document.mode == DocumentMode.study,
            )
        ).scalars()
        for doc_id in auto_ids:
            placement[doc_id] = None
            order[doc_id] = 0

    bookmarks: dict[int, bool] = {}
    items = session.execute(
        select(FolderItem).where(FolderItem.folder_id == folder_id)
    ).scalars()
    for item in items:
        placement[item.document_id] = item.group_id
        bookmarks[item.document_id] = item.bookmarked
        order[item.document_id] = item.order_index

    # Reuse the Library's summary builder so folder cards and Library cards
    # carry identical fields (topic counts, lane progress) with no second
    # implementation to keep in sync.
    summaries = {d.id: d for d in documentsvc.list_documents(session)}
    documents = [summaries[i] for i in placement if i in summaries]
    documents.sort(key=lambda d: (order.get(d.id, 0), d.id))

    # A promoted file is represented by the document it became, so listing both
    # would show the same material twice. Deleting that document sets the FK
    # back to NULL, which brings the raw file back into the listing.
    files = list(
        session.execute(
            select(FolderFile)
            .where(
                FolderFile.folder_id == folder_id,
                FolderFile.generated_document_id.is_(None),
            )
            .order_by(FolderFile.order_index, FolderFile.id)
        ).scalars()
    )

    children = list(
        session.execute(
            select(Folder)
            .where(Folder.parent_id == folder_id)
            .order_by(Folder.order_index, Folder.id)
        ).scalars()
    )

    return FolderContents(
        folder=folder,
        groups=groups,
        documents=documents,
        document_groups={d.id: placement[d.id] for d in documents},
        document_bookmarks={d.id: bookmarks.get(d.id, False) for d in documents},
        files=files,
        children=children,
    )


def create_folder(
    session: Session,
    *,
    name: str,
    parent_id: int | None = None,
    subject_id: int | None = None,
    tint: str | None = None,
    is_main: bool | None = None,
) -> Folder:
    """Create a folder, optionally tagged to a subject and/or nested one level.

    A folder tagged to a subject that has no main folder yet becomes the main
    one automatically, so tagging a subject for the first time behaves exactly
    as it did before the flag existed.
    """
    _assert_can_parent(session, parent_id)
    folder = Folder(
        name=name.strip(),
        parent_id=parent_id,
        subject_id=subject_id,
        tint=_normalize_tint(tint),
        order_index=_next_order(session, Folder, parent_id=parent_id),
    )
    session.add(folder)
    session.flush()
    if subject_id is not None and (
        is_main or not _subject_has_main(session, subject_id, excluding=folder.id)
    ):
        _claim_main(session, folder)
    session.commit()
    session.refresh(folder)
    return _decorate(session, [folder])[0]


def update_folder(
    session: Session,
    folder_id: int,
    *,
    name: str | None = None,
    tint: str | None = None,
    subject_id: int | None = None,
    clear_subject: bool = False,
    parent_id: int | None = None,
    clear_parent: bool = False,
    is_main: bool | None = None,
) -> Folder:
    """Patch a folder. ``clear_*`` flags exist because ``None`` already means
    "leave alone" for these two nullable columns."""
    folder = _get_folder(session, folder_id)
    if name is not None:
        folder.name = name.strip()
    if tint is not None:
        folder.tint = _normalize_tint(tint)
    if clear_subject:
        folder.subject_id = None
        folder.is_main = False  # nothing left to be the main folder of
    elif subject_id is not None:
        folder.subject_id = subject_id
    if clear_parent:
        folder.parent_id = None
    elif parent_id is not None:
        _assert_can_parent(session, parent_id, moving=folder_id)
        folder.parent_id = parent_id

    if folder.subject_id is not None:
        if is_main:
            _claim_main(session, folder)
        elif is_main is False:
            folder.is_main = False
        elif not _subject_has_main(session, folder.subject_id, excluding=folder.id):
            # Retagged onto a subject that has no main folder: take the role, so
            # a subject is never left with tagged folders but no main one.
            _claim_main(session, folder)

    session.commit()
    session.refresh(folder)
    return _decorate(session, [folder])[0]


def delete_folder(session: Session, folder_id: int) -> None:
    """Delete a folder, its children, groups and owned files.

    Documents are untouched: they belong to their subject, and this folder only
    referenced them.
    """
    folder = _get_folder(session, folder_id)
    orphaned_subject = folder.subject_id if folder.is_main else None
    session.delete(folder)
    session.commit()

    # Deleting the main folder would leave its subject with tagged folders that
    # all show nothing, and nowhere for new notes to land. Hand the role to the
    # oldest remaining tagged folder.
    if orphaned_subject is not None:
        successor = session.scalar(
            select(Folder)
            .where(Folder.subject_id == orphaned_subject)
            .order_by(Folder.id)
        )
        if successor is not None:
            _claim_main(session, successor)
            session.commit()


def reorder_folders(session: Session, folder_ids: list[int]) -> None:
    """Apply a drag-reorder. Ids not listed keep their current position."""
    for index, folder_id in enumerate(folder_ids):
        folder = session.get(Folder, folder_id)
        if folder is not None:
            folder.order_index = index
    session.commit()


def create_group(
    session: Session, folder_id: int, *, name: str, tint: str | None = None
) -> FolderGroup:
    """Add a named, colored band inside a folder."""
    _get_folder(session, folder_id)
    group = FolderGroup(
        folder_id=folder_id,
        name=name.strip(),
        tint=_normalize_tint(tint),
        order_index=_next_order(session, FolderGroup, folder_id=folder_id),
    )
    session.add(group)
    session.commit()
    session.refresh(group)
    return group


def update_group(
    session: Session,
    group_id: int,
    *,
    name: str | None = None,
    tint: str | None = None,
) -> FolderGroup:
    group = session.get(FolderGroup, group_id)
    if group is None:
        raise FolderGroupNotFoundError(group_id)
    if name is not None:
        group.name = name.strip()
    if tint is not None:
        group.tint = _normalize_tint(tint)
    session.commit()
    session.refresh(group)
    return group


def delete_group(session: Session, group_id: int) -> None:
    """Remove a group. Its contents stay in the folder, ungrouped (SET NULL)."""
    group = session.get(FolderGroup, group_id)
    if group is None:
        raise FolderGroupNotFoundError(group_id)
    session.delete(group)
    session.commit()


def _validate_group(session: Session, folder_id: int, group_id: int | None) -> None:
    """A group id is only meaningful within its own folder."""
    if group_id is None:
        return
    group = session.get(FolderGroup, group_id)
    if group is None or group.folder_id != folder_id:
        raise FolderGroupNotFoundError(group_id)


def add_documents(
    session: Session,
    folder_id: int,
    document_ids: list[int],
    *,
    group_id: int | None = None,
) -> list[FolderItem]:
    """Place documents in a folder — also the "copy into another folder" action.

    Already-present documents are skipped rather than erroring, so re-dropping
    a selection that partly overlaps behaves the way a user expects.
    """
    _get_folder(session, folder_id)
    _validate_group(session, folder_id, group_id)

    existing = set(
        session.execute(
            select(FolderItem.document_id).where(FolderItem.folder_id == folder_id)
        ).scalars()
    )
    order = _next_order(session, FolderItem, folder_id=folder_id)
    created: list[FolderItem] = []
    for document_id in document_ids:
        if document_id in existing or session.get(Document, document_id) is None:
            continue
        item = FolderItem(
            folder_id=folder_id,
            document_id=document_id,
            group_id=group_id,
            order_index=order,
        )
        order += 1
        session.add(item)
        created.append(item)
    session.commit()
    return created


def _ensure_item(session: Session, folder_id: int, document_id: int) -> FolderItem:
    """The document's placement row in this folder, created if it has none.

    Subject-tagged members are computed rather than stored, so any per-folder
    state they acquire (a group, a bookmark) has to materialize the row first.
    That is what makes those flags per-folder: the same document can be starred
    in one folder and untouched in another.
    """
    item = session.scalar(
        select(FolderItem).where(
            FolderItem.folder_id == folder_id, FolderItem.document_id == document_id
        )
    )
    if item is None:
        item = FolderItem(
            folder_id=folder_id,
            document_id=document_id,
            order_index=_next_order(session, FolderItem, folder_id=folder_id),
        )
        session.add(item)
    return item


def set_document_group(
    session: Session, folder_id: int, document_id: int, group_id: int | None
) -> FolderItem:
    """Move a document into (or out of) a group within a folder."""
    _get_folder(session, folder_id)
    _validate_group(session, folder_id, group_id)
    item = _ensure_item(session, folder_id, document_id)
    item.group_id = group_id
    session.commit()
    session.refresh(item)
    return item


def set_document_bookmark(
    session: Session, folder_id: int, document_id: int, bookmarked: bool
) -> FolderItem:
    """Star a note *within one folder*, leaving it unstarred elsewhere."""
    _get_folder(session, folder_id)
    item = _ensure_item(session, folder_id, document_id)
    item.bookmarked = bookmarked
    session.commit()
    session.refresh(item)
    return item


def set_folder_bookmark(session: Session, folder_id: int, bookmarked: bool) -> Folder:
    """Star a folder; the Library's bookmark filter narrows to these."""
    folder = _get_folder(session, folder_id)
    folder.bookmarked = bookmarked
    session.commit()
    session.refresh(folder)
    return _decorate(session, [folder])[0]


def remove_document(session: Session, folder_id: int, document_id: int) -> None:
    """Drop a manual placement. A document that is *also* an auto member of this
    folder stays visible, because the subject tag still matches it."""
    session.execute(
        delete(FolderItem).where(
            FolderItem.folder_id == folder_id, FolderItem.document_id == document_id
        )
    )
    session.commit()


def _kind_for(content_type: str) -> str:
    ct = (content_type or "").lower()
    if ct == "application/pdf":
        return "pdf"
    if ct.split("/", 1)[0] == "image":
        return "image"
    raise UnsupportedFolderFileError(content_type)


def add_file(
    session: Session,
    folder_id: int,
    *,
    filename: str,
    content_type: str,
    data: bytes,
    group_id: int | None = None,
) -> FolderFile:
    """Store a PDF/image dropped straight into a folder. Inert until promoted."""
    if not data:
        raise UnsupportedFolderFileError("empty file")
    if len(data) > MAX_FOLDER_FILE_BYTES:
        raise UnsupportedFolderFileError("file too large")
    kind = _kind_for(content_type)
    _get_folder(session, folder_id)
    _validate_group(session, folder_id, group_id)

    file = FolderFile(
        folder_id=folder_id,
        group_id=group_id,
        kind=kind,
        filename=filename,
        content_type=content_type,
        file_hash=persist_bytes(data, filename),
        order_index=_next_order(session, FolderFile, folder_id=folder_id),
    )
    session.add(file)
    session.commit()
    session.refresh(file)
    return file


def get_file(session: Session, file_id: int) -> FolderFile:
    file = session.get(FolderFile, file_id)
    if file is None:
        raise FolderFileNotFoundError(file_id)
    return file


def file_path(file: FolderFile) -> Path:
    """Where the bytes live, in the store shared with note/chat attachments."""
    return store_path(file.file_hash, file.filename)


def delete_file(session: Session, file_id: int) -> None:
    """Delete a loose file, releasing its bytes if nothing else references them."""
    file = get_file(session, file_id)
    file_hash, filename = file.file_hash, file.filename
    session.delete(file)
    session.commit()
    release_file(session, file_hash, filename)


def generate_notes(
    session: Session,
    file_id: int,
    *,
    subject_id: int | None = None,
    ingest_fn: IngestFn = ingest,
    uploads_dir: str | Path = UPLOADS_DIR,
) -> Document:
    """Promote an inert PDF into a real Document, ready for structure review.

    Idempotent through ``generated_document_id``: a second call returns the
    document the first one made rather than re-ingesting the same bytes. If that
    document has since been deleted the FK is already NULL (SET NULL), so the
    file becomes promotable again.

    The new document is also placed in the folder via a ``FolderItem`` in the
    file's group, so it lands exactly where the file was sitting instead of only
    showing up if the folder happens to be tagged to its subject.
    """
    file = get_file(session, file_id)
    if file.generated_document_id is not None:
        existing = session.get(Document, file.generated_document_id)
        if existing is not None:
            return existing
    # Images have no text to build notes from; only PDFs can be promoted.
    if file.kind != "pdf":
        raise UnsupportedFolderFileError(file.kind)

    folder = _get_folder(session, file.folder_id)
    target_subject = subject_id if subject_id is not None else folder.subject_id
    if target_subject is None:
        raise MissingSubjectError(file.folder_id)

    path = file_path(file)
    if not path.is_file():
        raise FolderFileNotFoundError(file_id)

    # ``ingest_fn``/``uploads_dir`` are threaded through rather than left to
    # create_document's defaults, matching how the rest of the codebase makes
    # ingestion injectable for tests.
    document, _ = documentsvc.create_document(
        session,
        subject_id=target_subject,
        filename=file.filename,
        data=path.read_bytes(),
        ingest_fn=ingest_fn,
        uploads_dir=uploads_dir,
    )
    file.generated_document_id = document.id
    session.add(
        FolderItem(
            folder_id=file.folder_id,
            document_id=document.id,
            group_id=file.group_id,
            order_index=_next_order(session, FolderItem, folder_id=file.folder_id),
        )
    )
    session.commit()
    session.refresh(document)
    return document
