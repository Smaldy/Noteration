"""Search service + HTTP tests: title match, subject scoping, topic-first order."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

import backend.models  # noqa: F401 - register models on Base.metadata
from backend.models import Chapter, Document, Subject, Topic
from backend.models.enums import TopicPriority, TopicStatus
from backend.services import search as search_service


def _seed(session: Session) -> dict[str, int]:
    """Two subjects with chapters/topics that share a search term ('wave')."""
    physics = Subject(name="Physics")
    maths = Subject(name="Maths")
    session.add_all([physics, maths])
    session.flush()

    phys_doc = Document(subject_id=physics.id, filename="physics.pdf", file_hash="p")
    math_doc = Document(subject_id=maths.id, filename="maths.pdf", file_hash="m")
    session.add_all([phys_doc, math_doc])
    session.flush()

    waves_ch = Chapter(
        document_id=phys_doc.id, subject_id=physics.id, title="Wave mechanics"
    )
    fourier_ch = Chapter(
        document_id=math_doc.id, subject_id=maths.id, title="Fourier analysis"
    )
    session.add_all([waves_ch, fourier_ch])
    session.flush()

    standing = Topic(
        chapter_id=waves_ch.id,
        title="Standing waves",
        priority=TopicPriority.exam_critical,
        status=TopicStatus.ready,
    )
    wavelets = Topic(chapter_id=fourier_ch.id, title="Wavelet transforms")
    kinematics = Topic(chapter_id=waves_ch.id, title="Kinematics")
    session.add_all([standing, wavelets, kinematics])
    session.commit()
    return {
        "physics": physics.id,
        "maths": maths.id,
        "standing": standing.id,
        "wavelets": wavelets.id,
        "waves_ch": waves_ch.id,
        "phys_doc": phys_doc.id,
    }


# --- service unit tests ------------------------------------------------------


def test_search_matches_topics_then_chapters(session: Session) -> None:
    ids = _seed(session)
    hits = search_service.search(session, query="wave")
    kinds = {(h.kind, h.title) for h in hits}
    # Two topics ("Standing waves", "Wavelet transforms") + one chapter ("Wave mechanics").
    assert ("topic", "Standing waves") in kinds
    assert ("topic", "Wavelet transforms") in kinds
    assert ("chapter", "Wave mechanics") in kinds
    # Topics rank ahead of chapters.
    assert [h.kind for h in hits].index("chapter") > [
        h.kind for h in hits
    ].index("topic")
    # Topic hits carry their breadcrumb + status/priority.
    standing = next(h for h in hits if h.title == "Standing waves")
    assert standing.subject_name == "Physics"
    assert standing.chapter_title == "Wave mechanics"
    assert standing.document_id == ids["phys_doc"]
    assert standing.status is TopicStatus.ready
    assert standing.priority is TopicPriority.exam_critical


def test_search_is_case_insensitive(session: Session) -> None:
    _seed(session)
    assert search_service.search(session, query="STANDING")
    assert search_service.search(session, query="standing")


def test_search_scopes_to_subject(session: Session) -> None:
    ids = _seed(session)
    physics_only = search_service.search(session, query="wave", subject_id=ids["physics"])
    titles = {h.title for h in physics_only}
    assert "Standing waves" in titles
    assert "Wave mechanics" in titles
    assert "Wavelet transforms" not in titles  # that topic is under Maths


def test_search_blank_query_returns_nothing(session: Session) -> None:
    _seed(session)
    assert search_service.search(session, query="   ") == []


def test_search_wildcards_are_literal(session: Session) -> None:
    _seed(session)
    # '%' must not behave as a wildcard; nothing literally contains it.
    assert search_service.search(session, query="%") == []


# --- HTTP tests --------------------------------------------------------------


def test_http_search_returns_hits(client: TestClient, db_factory: sessionmaker) -> None:
    seed = db_factory()
    _seed(seed)
    seed.close()

    response = client.get("/api/search", params={"q": "wave"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert any(r["kind"] == "topic" and r["title"] == "Standing waves" for r in body)
    assert any(r["kind"] == "chapter" for r in body)


def test_http_search_requires_query(client: TestClient) -> None:
    assert client.get("/api/search").status_code == 422  # q is required


def test_http_search_limit_is_capped(client: TestClient) -> None:
    assert client.get("/api/search", params={"q": "x", "limit": 0}).status_code == 422
    assert client.get("/api/search", params={"q": "x", "limit": 999}).status_code == 422
