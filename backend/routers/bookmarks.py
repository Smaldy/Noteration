"""/bookmarks — the bookmarked subjects + topics for the Bookmarks view."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.db.database import get_session
from backend.schemas.bookmarks import BookmarksOut
from backend.services import bookmarks as bookmarks_service

router = APIRouter(prefix="/bookmarks", tags=["bookmarks"])


@router.get("", response_model=BookmarksOut)
def list_bookmarks(session: Session = Depends(get_session)) -> BookmarksOut:
    """All bookmarked subjects and topics in one read."""
    result = bookmarks_service.list_bookmarks(session)
    return BookmarksOut(subjects=result.subjects, topics=result.topics)
