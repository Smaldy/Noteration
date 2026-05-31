"""Shared schema for manual reordering (documents, topics)."""

from __future__ import annotations

from pydantic import BaseModel


class ReorderRequest(BaseModel):
    """Ordered ids; each item's ``order_index`` is set to its position."""

    ids: list[int]
