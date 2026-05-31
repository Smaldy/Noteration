"""/search — title search over topics and chapters, optionally subject-scoped."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.db.database import get_session
from backend.schemas.search import SearchResultOut
from backend.services import search as search_service

router = APIRouter(prefix="/search", tags=["search"])


@router.get("", response_model=list[SearchResultOut])
def search(
    q: str = Query(min_length=1, max_length=200),
    subject_id: int | None = Query(default=None),
    limit: int = Query(default=30, ge=1, le=100),
    session: Session = Depends(get_session),
) -> list[search_service.SearchHit]:
    """Find topics (then chapters) whose title contains ``q``."""
    return search_service.search(session, query=q, subject_id=subject_id, limit=limit)
