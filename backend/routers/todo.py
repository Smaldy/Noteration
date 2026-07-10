"""/todo — the floating to-do list (pinned topics)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from backend.db.database import get_session
from backend.schemas.todo import TodoAddRequest, TodoClearedOut, TodoItemOut
from backend.services import todo as todo_service

router = APIRouter(prefix="/todo", tags=["todo"])


@router.get("", response_model=list[TodoItemOut])
def list_todo(db: Session = Depends(get_session)) -> list:
    """The full to-do list in the order topics were added."""
    return todo_service.list_items(db)


@router.post("", response_model=list[TodoItemOut])
def add_to_todo(
    payload: TodoAddRequest,
    db: Session = Depends(get_session),
) -> list:
    """Pin topics to the list (idempotent) and return the refreshed list."""
    return todo_service.add_topics(db, payload.topic_ids)


@router.delete("/completed", response_model=TodoClearedOut)
def clear_completed(db: Session = Depends(get_session)) -> TodoClearedOut:
    """Remove every checked-off (studied) item from the list."""
    return TodoClearedOut(removed=todo_service.clear_completed(db))


@router.delete("/{topic_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_from_todo(
    topic_id: int,
    db: Session = Depends(get_session),
) -> Response:
    """Unpin one topic from the list."""
    if not todo_service.remove_topic(db, topic_id):
        raise HTTPException(status_code=404, detail="Topic is not on the to-do list")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
