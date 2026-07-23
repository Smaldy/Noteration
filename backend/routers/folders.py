"""Folders router — the Library's organizing layer.

Thin: delegates to ``services.folders``. Routes are ordered so the literal
``/files/...`` prefix is matched before ``/{folder_id}``, which would otherwise
swallow it.
"""

from __future__ import annotations

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from backend.db.database import get_session
from backend.models import Folder, FolderFile, FolderGroup
from backend.schemas.folder import (
    BookmarkUpdate,
    FolderContentsOut,
    FolderCreate,
    FolderDocumentGroupUpdate,
    FolderDocumentsAdd,
    FolderFileOut,
    FolderGroupCreate,
    FolderGroupOut,
    FolderGroupUpdate,
    FolderOut,
    FolderUpdate,
    GeneratedNotesOut,
    GenerateNotesIn,
)
from backend.schemas.reorder import ReorderRequest
from backend.services import documents as docsvc
from backend.services import folders as foldersvc

router = APIRouter(prefix="/folders", tags=["folders"])


@router.get("", response_model=list[FolderOut])
def list_folders(session: Session = Depends(get_session)) -> list[Folder]:
    """Every folder in display order, with item and child counts."""
    return foldersvc.list_folders(session)


@router.post("", response_model=FolderOut, status_code=201)
def create_folder(
    payload: FolderCreate,
    session: Session = Depends(get_session),
) -> Folder:
    """Create a folder, optionally subject-tagged and/or nested one level."""
    try:
        return foldersvc.create_folder(
            session,
            name=payload.name,
            parent_id=payload.parent_id,
            subject_id=payload.subject_id,
            tint=payload.tint,
            is_main=payload.is_main,
        )
    except foldersvc.FolderNotFoundError:
        raise HTTPException(status_code=404, detail="Parent folder not found")
    except foldersvc.FolderDepthError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.put("/reorder", status_code=status.HTTP_204_NO_CONTENT)
def reorder_folders(
    payload: ReorderRequest,
    session: Session = Depends(get_session),
) -> Response:
    """Persist a drag-reorder of the folder grid."""
    foldersvc.reorder_folders(session, payload.ids)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Loose files -----------------------------------------------------------
# Declared before /{folder_id} so "files" isn't parsed as a folder id.


@router.get("/files/{file_id}/raw")
def get_folder_file(
    file_id: int,
    session: Session = Depends(get_session),
) -> FileResponse:
    """Serve a loose file's bytes with its stored content type."""
    try:
        file = foldersvc.get_file(session, file_id)
    except foldersvc.FolderFileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found")
    path = foldersvc.file_path(file)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="File missing from store")
    return FileResponse(path, media_type=file.content_type, filename=file.filename)


@router.post("/files/{file_id}/generate", response_model=GeneratedNotesOut)
def generate_notes(
    file_id: int,
    payload: GenerateNotesIn,
    session: Session = Depends(get_session),
) -> dict[str, int]:
    """Promote an inert PDF into a Document and hand back its review route."""
    try:
        document = foldersvc.generate_notes(
            session, file_id, subject_id=payload.subject_id
        )
    except foldersvc.FolderFileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found")
    except foldersvc.MissingSubjectError:
        raise HTTPException(
            status_code=422,
            detail="Pick a subject, or tag this folder to one.",
        )
    except foldersvc.UnsupportedFolderFileError:
        raise HTTPException(
            status_code=415, detail="Only PDFs can be turned into notes."
        )
    except docsvc.SubjectNotFoundError:
        raise HTTPException(status_code=404, detail="Subject not found")
    except docsvc.InvalidPDFError:
        raise HTTPException(status_code=415, detail="That file is not a valid PDF.")
    return {"document_id": document.id}


@router.delete("/files/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_folder_file(
    file_id: int,
    session: Session = Depends(get_session),
) -> Response:
    """Delete a loose file (removes its bytes if unreferenced)."""
    try:
        foldersvc.delete_file(session, file_id)
    except foldersvc.FolderFileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Groups ----------------------------------------------------------------


@router.patch("/groups/{group_id}", response_model=FolderGroupOut)
def update_group(
    group_id: int,
    payload: FolderGroupUpdate,
    session: Session = Depends(get_session),
) -> FolderGroup:
    """Rename or recolor a sub-group."""
    try:
        return foldersvc.update_group(
            session, group_id, name=payload.name, tint=payload.tint
        )
    except foldersvc.FolderGroupNotFoundError:
        raise HTTPException(status_code=404, detail="Group not found")


@router.delete("/groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_group(
    group_id: int,
    session: Session = Depends(get_session),
) -> Response:
    """Delete a sub-group; its contents stay in the folder, ungrouped."""
    try:
        foldersvc.delete_group(session, group_id)
    except foldersvc.FolderGroupNotFoundError:
        raise HTTPException(status_code=404, detail="Group not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- One folder ------------------------------------------------------------


@router.get("/{folder_id}", response_model=FolderContentsOut)
def get_folder(
    folder_id: int,
    session: Session = Depends(get_session),
) -> foldersvc.FolderContents:
    """One folder resolved: groups, documents, loose files, child folders."""
    try:
        return foldersvc.get_contents(session, folder_id)
    except foldersvc.FolderNotFoundError:
        raise HTTPException(status_code=404, detail="Folder not found")


@router.patch("/{folder_id}", response_model=FolderOut)
def update_folder(
    folder_id: int,
    payload: FolderUpdate,
    session: Session = Depends(get_session),
) -> Folder:
    """Rename, recolor, retag or reparent a folder."""
    try:
        return foldersvc.update_folder(
            session,
            folder_id,
            name=payload.name,
            tint=payload.tint,
            subject_id=payload.subject_id,
            clear_subject=payload.clear_subject,
            parent_id=payload.parent_id,
            clear_parent=payload.clear_parent,
            is_main=payload.is_main,
        )
    except foldersvc.FolderNotFoundError:
        raise HTTPException(status_code=404, detail="Folder not found")
    except foldersvc.FolderDepthError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.delete("/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_folder(
    folder_id: int,
    session: Session = Depends(get_session),
) -> Response:
    """Delete a folder and its children. Documents are left untouched."""
    try:
        foldersvc.delete_folder(session, folder_id)
    except foldersvc.FolderNotFoundError:
        raise HTTPException(status_code=404, detail="Folder not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{folder_id}/groups", response_model=FolderGroupOut, status_code=201)
def create_group(
    folder_id: int,
    payload: FolderGroupCreate,
    session: Session = Depends(get_session),
) -> FolderGroup:
    """Add a named, colored band inside a folder."""
    try:
        return foldersvc.create_group(
            session, folder_id, name=payload.name, tint=payload.tint
        )
    except foldersvc.FolderNotFoundError:
        raise HTTPException(status_code=404, detail="Folder not found")


@router.post("/{folder_id}/documents", status_code=status.HTTP_204_NO_CONTENT)
def add_documents(
    folder_id: int,
    payload: FolderDocumentsAdd,
    session: Session = Depends(get_session),
) -> Response:
    """Place documents in a folder. Also the copy-into-another-folder action."""
    try:
        foldersvc.add_documents(
            session, folder_id, payload.document_ids, group_id=payload.group_id
        )
    except foldersvc.FolderNotFoundError:
        raise HTTPException(status_code=404, detail="Folder not found")
    except foldersvc.FolderGroupNotFoundError:
        raise HTTPException(status_code=404, detail="Group not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put(
    "/{folder_id}/documents/{document_id}/group", status_code=status.HTTP_204_NO_CONTENT
)
def set_document_group(
    folder_id: int,
    document_id: int,
    payload: FolderDocumentGroupUpdate,
    session: Session = Depends(get_session),
) -> Response:
    """File a document into a sub-group, or back out of one."""
    try:
        foldersvc.set_document_group(session, folder_id, document_id, payload.group_id)
    except foldersvc.FolderNotFoundError:
        raise HTTPException(status_code=404, detail="Folder not found")
    except foldersvc.FolderGroupNotFoundError:
        raise HTTPException(status_code=404, detail="Group not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/{folder_id}/bookmark", response_model=FolderOut)
def set_folder_bookmark(
    folder_id: int,
    payload: BookmarkUpdate,
    session: Session = Depends(get_session),
) -> Folder:
    """Star a folder. The Library's bookmark filter narrows to these."""
    try:
        return foldersvc.set_folder_bookmark(session, folder_id, payload.bookmarked)
    except foldersvc.FolderNotFoundError:
        raise HTTPException(status_code=404, detail="Folder not found")


@router.put(
    "/{folder_id}/documents/{document_id}/bookmark",
    status_code=status.HTTP_204_NO_CONTENT,
)
def set_document_bookmark(
    folder_id: int,
    document_id: int,
    payload: BookmarkUpdate,
    session: Session = Depends(get_session),
) -> Response:
    """Star a note inside one folder, leaving it unstarred elsewhere."""
    try:
        foldersvc.set_document_bookmark(
            session, folder_id, document_id, payload.bookmarked
        )
    except foldersvc.FolderNotFoundError:
        raise HTTPException(status_code=404, detail="Folder not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/{folder_id}/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT
)
def remove_document(
    folder_id: int,
    document_id: int,
    session: Session = Depends(get_session),
) -> Response:
    """Remove a manual placement. Subject-tagged members stay (still matched)."""
    foldersvc.remove_document(session, folder_id, document_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{folder_id}/files", response_model=FolderFileOut, status_code=201)
def add_file(
    folder_id: int,
    file: UploadFile = File(...),
    group_id: int | None = Form(default=None),
    session: Session = Depends(get_session),
) -> FolderFile:
    """Drop a PDF or image straight into a folder. Inert until promoted."""
    data = file.file.read()
    try:
        return foldersvc.add_file(
            session,
            folder_id,
            filename=file.filename or "file",
            content_type=file.content_type or "",
            data=data,
            group_id=group_id,
        )
    except foldersvc.FolderNotFoundError:
        raise HTTPException(status_code=404, detail="Folder not found")
    except foldersvc.FolderGroupNotFoundError:
        raise HTTPException(status_code=404, detail="Group not found")
    except foldersvc.UnsupportedFolderFileError as exc:
        raise HTTPException(status_code=415, detail=str(exc))
