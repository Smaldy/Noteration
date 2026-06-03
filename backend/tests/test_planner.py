"""AI study planner: parse, prompt, and plan generation/persistence."""

from __future__ import annotations

import json
import uuid
from datetime import date, timedelta

import pytest

from backend.models import Chapter, Document, ScheduleEntry, Subject, Topic
from backend.models.enums import ScheduleSource, TopicPriority
from backend.services import planner
from backend.services.providers.mock import MockProvider
from backend.services.providers.waterfall import Waterfall

TODAY = date.today()
D = timedelta(days=1)


def _seed(session, *, exam_in_days: int | None = 20, topics=None):
    topics = topics or [("Kinematics", TopicPriority.exam_critical), ("Energy", TopicPriority.medium)]
    exam = TODAY + exam_in_days * D if exam_in_days is not None else None
    subj = Subject(name="Physics", exam_date=exam)
    session.add(subj)
    session.flush()
    doc = Document(subject_id=subj.id, filename="f.pdf", file_hash=uuid.uuid4().hex)
    session.add(doc)
    session.flush()
    ch = Chapter(document_id=doc.id, subject_id=subj.id, title="Ch")
    session.add(ch)
    session.flush()
    ids = []
    for title, prio in topics:
        t = Topic(chapter_id=ch.id, title=title, priority=prio)
        session.add(t)
        session.flush()
        ids.append(t.id)
    session.commit()
    return subj.id, ids


def _waterfall(plan: dict) -> Waterfall:
    return Waterfall([MockProvider("mock", text=json.dumps(plan))])


# --- parsing ---------------------------------------------------------------- #


def test_parse_plan_valid():
    text = json.dumps(
        {"sessions": [{"topic_id": 3, "date": "2026-06-10", "note": "intro"}]}
    )
    sessions = planner.parse_plan(text)
    assert len(sessions) == 1
    assert sessions[0].topic_id == 3
    assert sessions[0].on_date == date(2026, 6, 10)
    assert sessions[0].note == "intro"


def test_parse_plan_skips_malformed_items():
    text = json.dumps(
        {
            "sessions": [
                {"topic_id": "x", "date": "2026-06-10"},  # bad id
                {"topic_id": 1, "date": "not-a-date"},  # bad date
                {"topic_id": 2, "date": "2026-06-11"},  # good
            ]
        }
    )
    sessions = planner.parse_plan(text)
    assert [s.topic_id for s in sessions] == [2]


def test_parse_plan_empty_raises():
    with pytest.raises(planner.PlanParseError):
        planner.parse_plan(json.dumps({"sessions": []}))


def test_build_plan_prompt_lists_topic_ids(session):
    _subj, ids = _seed(session)
    topics = session.query(Topic).all()
    prompt = planner.build_plan_prompt(
        "Physics", topics, today=TODAY, start=TODAY, end=TODAY + 18 * D
    )
    for tid in ids:
        assert f"id={tid}" in prompt
    assert "exam_critical" in prompt


# --- generation ------------------------------------------------------------- #


def test_generate_creates_ai_entries_within_window(session):
    subj_id, ids = _seed(session)
    plan = {
        "sessions": [
            {"topic_id": ids[0], "date": (TODAY + 1 * D).isoformat(), "note": "start"},
            {"topic_id": ids[1], "date": (TODAY + 3 * D).isoformat(), "note": "next"},
        ]
    }
    entries = planner.generate_study_plan(
        session, subj_id, waterfall=_waterfall(plan), today=TODAY
    )
    assert len(entries) == 2
    assert all(e.source == ScheduleSource.ai for e in entries)
    assert all(e.subject_id == subj_id for e in entries)
    # description carries the model's note; title defaults to the topic title.
    by_topic = {e.topic_id: e for e in entries}
    assert by_topic[ids[0]].description == "start"
    assert by_topic[ids[0]].title == "Kinematics"


def test_generate_clamps_and_drops_invalid_ids(session):
    subj_id, ids = _seed(session, exam_in_days=20)
    plan = {
        "sessions": [
            {"topic_id": ids[0], "date": (TODAY + 100 * D).isoformat()},  # past window
            {"topic_id": ids[1], "date": (TODAY - 5 * D).isoformat()},  # before today
            {"topic_id": 999999, "date": (TODAY + 2 * D).isoformat()},  # hallucinated
        ]
    }
    entries = planner.generate_study_plan(
        session, subj_id, waterfall=_waterfall(plan), today=TODAY
    )
    assert len(entries) == 2  # invalid id dropped
    window_end = (TODAY + 20 * D) - timedelta(days=2)  # exam - revision buffer
    dates = {e.topic_id: e.date for e in entries}
    assert dates[ids[0]] == window_end  # clamped down into window
    assert dates[ids[1]] == TODAY  # clamped up to today


def test_replan_replaces_ai_keeps_manual(session):
    subj_id, ids = _seed(session)
    # A user manual event on a topic — must survive re-planning.
    manual = ScheduleEntry(
        topic_id=ids[0], date=TODAY + 2 * D, source=ScheduleSource.manual, title="mine"
    )
    session.add(manual)
    session.commit()

    planner.generate_study_plan(
        session,
        subj_id,
        waterfall=_waterfall(
            {"sessions": [{"topic_id": ids[0], "date": (TODAY + 1 * D).isoformat()}]}
        ),
        today=TODAY,
    )
    # Re-plan: prior AI entries gone, new one in; manual still present.
    planner.generate_study_plan(
        session,
        subj_id,
        waterfall=_waterfall(
            {"sessions": [{"topic_id": ids[1], "date": (TODAY + 4 * D).isoformat()}]}
        ),
        today=TODAY,
    )
    ai = session.query(ScheduleEntry).filter_by(source=ScheduleSource.ai).all()
    assert len(ai) == 1 and ai[0].topic_id == ids[1]
    assert session.query(ScheduleEntry).filter_by(source=ScheduleSource.manual).count() == 1


def test_generate_no_topics_raises(session):
    subj = Subject(name="Empty")
    session.add(subj)
    session.commit()
    with pytest.raises(planner.NoTopicsToPlanError):
        planner.generate_study_plan(
            session, subj.id, waterfall=_waterfall({"sessions": []}), today=TODAY
        )


def test_generate_unknown_subject_raises(session):
    with pytest.raises(planner.SubjectNotFoundError):
        planner.generate_study_plan(
            session, 999, waterfall=_waterfall({"sessions": []}), today=TODAY
        )


def test_skips_studied_topics(session):
    subj_id, ids = _seed(session)
    # Mark the first topic studied — it should be excluded from the plan.
    session.get(Topic, ids[0]).studied = True
    session.commit()
    plan = {
        "sessions": [
            {"topic_id": ids[0], "date": (TODAY + 1 * D).isoformat()},
            {"topic_id": ids[1], "date": (TODAY + 2 * D).isoformat()},
        ]
    }
    entries = planner.generate_study_plan(
        session, subj_id, waterfall=_waterfall(plan), today=TODAY
    )
    # Even though the model returned the studied topic, it's not a valid id for
    # this plan (excluded), so only the unstudied topic lands.
    assert {e.topic_id for e in entries} == {ids[1]}


def test_studied_topic_ids_persists_and_excludes(session):
    subj_id, ids = _seed(session)
    plan = {"sessions": [{"topic_id": ids[1], "date": (TODAY + 2 * D).isoformat()}]}
    planner.generate_study_plan(
        session,
        subj_id,
        waterfall=_waterfall(plan),
        today=TODAY,
        studied_topic_ids=[ids[0]],
    )
    assert session.get(Topic, ids[0]).studied is True
    assert session.get(Topic, ids[1]).studied is False


def test_all_studied_raises(session):
    subj_id, ids = _seed(session)
    with pytest.raises(planner.NoTopicsToPlanError):
        planner.generate_study_plan(
            session,
            subj_id,
            waterfall=_waterfall({"sessions": []}),
            today=TODAY,
            studied_topic_ids=ids,  # every topic studied
        )


def test_delete_plan_removes_only_ai(session):
    subj_id, ids = _seed(session)
    session.add_all(
        [
            ScheduleEntry(topic_id=ids[0], date=TODAY + 1 * D, source=ScheduleSource.ai),
            ScheduleEntry(topic_id=ids[1], date=TODAY + 2 * D, source=ScheduleSource.manual),
        ]
    )
    session.commit()
    deleted = planner.delete_plan(session, subj_id)
    assert deleted == 1
    remaining = session.query(ScheduleEntry).all()
    assert [e.source for e in remaining] == [ScheduleSource.manual]


def test_prompt_mentions_deadline(session):
    _subj, ids = _seed(session, exam_in_days=20)
    topics = session.query(Topic).all()
    exam = TODAY + 20 * D
    prompt = planner.build_plan_prompt(
        "Physics", topics, today=TODAY, start=TODAY, end=exam, exam_date=exam
    )
    assert exam.isoformat() in prompt
    assert "deadline" in prompt.lower()


def test_no_exam_date_uses_default_horizon(session):
    subj_id, ids = _seed(session, exam_in_days=None)
    entries = planner.generate_study_plan(
        session,
        subj_id,
        waterfall=_waterfall(
            {"sessions": [{"topic_id": ids[0], "date": (TODAY + 5 * D).isoformat()}]}
        ),
        today=TODAY,
    )
    assert len(entries) == 1
    assert entries[0].date == TODAY + 5 * D  # within the 14-day default window
